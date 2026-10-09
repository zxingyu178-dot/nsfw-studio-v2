"""EngineAdapter 工厂 + Workflow 模块身份解析。

- 按 configs 选择引擎实现（不修改核心）；
- Phase 3 §五：Job 创建时把请求的 workflow_modules 解析为**真实身份列表**
  （module/provider/binding_version/workflow_hash），作为 Pipeline 的唯一执行真源；
- Phase 4 Task1：身份列表同时携带 binding_hash（binding.yaml 指纹）；
- Phase 4 Task9：请求项若携带完整执行身份（从历史 Job / Image 恢复）→ 固定使用原身份
  （comfyui 下先做指纹/自描述校验），禁止静默升级到当前默认版本；
  普通新建工作台只携带 module_id → 由后端解析当前默认版本。
- Task11：创建 Studio Input Registry 并注入 Adapter（输入文件 TTL 清理用）。
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.engine.base import EngineAdapter, EngineBindingRef, EngineError
from app.engine.input_registry import REGISTRY_FILENAME, EngineInputRegistry

# 执行身份字段（EngineBindingRef 等价）：任何一项存在即视为"携带身份"
_IDENTITY_KEYS = ("module_version", "provider", "binding_version", "workflow_hash", "binding_hash")


def make_input_registry(settings: Settings) -> EngineInputRegistry:
    return EngineInputRegistry(settings.storage.data_root / REGISTRY_FILENAME)


def create_engine_adapter(settings: Settings) -> EngineAdapter:
    engine_cfg = (settings.workflow.raw or {}).get("engine") or {}
    provider = engine_cfg.get("provider", "unbound")
    options = engine_cfg.get("options") or {}
    registry = make_input_registry(settings)

    if provider == "mock":
        from app.engine.mock import MockEngineAdapter

        return MockEngineAdapter(options, input_registry=registry)
    if provider == "comfyui":
        from app.engine.comfyui import ComfyUIAdapter

        # §0.2：Adapter 不再携带实例级 binding；身份来自每次 EngineJobRequest
        return ComfyUIAdapter(options, comfyui_config=settings.comfyui, input_registry=registry)
    from app.engine.unbound import UnboundEngineAdapter

    return UnboundEngineAdapter()


def _pinned_identity(entry: dict) -> dict[str, str | None] | None:
    """从请求项提取"完整执行身份"（Task9）；任一身字段缺失 → 视为普通新建（None）。"""
    module_id = str(entry.get("module_id") or "").strip()
    if not module_id:
        return None
    if not any(entry.get(key) for key in _IDENTITY_KEYS):
        return None
    if not entry.get("module_version") or not entry.get("provider") or not entry.get("binding_version"):
        return None
    return {
        "module_id": module_id,
        "module_version": str(entry["module_version"]),
        "provider": str(entry["provider"]),
        "binding_version": str(entry["binding_version"]),
        "workflow_hash": entry.get("workflow_hash"),
        "binding_hash": entry.get("binding_hash"),
    }


def resolve_workflow_modules(settings: Settings, requested: list[dict] | None) -> list[dict]:
    """请求的模块列表 → 真实身份列表（§五；默认仅基础生成）。

    每项输出 {module_id, module_version, provider, binding_version, workflow_hash, binding_hash}；
    - 普通新建（只有 module_id）：comfyui 时从 provider binding 读取真实 binding_version 与两个指纹；
    - 从历史恢复（携带完整身份，Task9）：固定使用原身份，禁止静默升级；
      comfyui 下必须通过 load_binding 校验（BINDING_NOT_FOUND / WORKFLOW_HASH_MISMATCH /
      BINDING_HASH_MISMATCH / BINDING_IDENTITY_MISMATCH 直接拒绝）。
    Phase 6 Task4：
    - **严格保持请求顺序**（不再按硬编码 MODULE_ORDER 重排——
      否则 reference_generate → upscale 会被错误重排成 upscale → reference_generate；
      合法性由 PipelineValidator + ModuleCapabilities 校验）；
    - 同一 module_id 在 Pipeline 中重复出现 → PIPELINE_DUPLICATE_MODULE（第一版禁止）。
    """
    engine_cfg = (settings.workflow.raw or {}).get("engine") or {}
    provider = str(engine_cfg.get("provider", "unbound"))
    modules_cfg = engine_cfg.get("modules") or {}
    default_module = str(engine_cfg.get("module_id", "basic_generate"))

    entries: dict[str, dict] = {}
    ids: list[str] = []
    for entry in requested or []:
        module_id = str((entry or {}).get("module_id") or "").strip()
        if not module_id:
            continue
        if module_id in entries:
            raise EngineError(
                "PIPELINE_DUPLICATE_MODULE",
                f"Pipeline 不允许同一模块重复出现: {module_id}",
            )
        ids.append(module_id)
        entries[module_id] = dict(entry or {})
    if not ids:
        ids = [default_module]

    identities: list[dict] = []
    adapter = None
    for module_id in ids:
        pinned = _pinned_identity(entries.get(module_id) or {})
        if pinned is not None:
            if pinned["provider"] != provider:
                raise EngineError(
                    "BINDING_IDENTITY_MISMATCH",
                    f"原工作流使用 {pinned['provider']} 引擎，当前引擎为 {provider}，无法精确重现",
                )
            if provider == "comfyui":
                if adapter is None:
                    from app.engine.comfyui import ComfyUIAdapter

                    adapter = ComfyUIAdapter(engine_cfg.get("options") or {}, comfyui_config=settings.comfyui)
                # 校验指纹与自描述；磁盘两个指纹为准（老 Job 允许 null → 采纳磁盘当前值）
                _workflow, binding, workflow_hash, binding_hash = adapter.load_binding(
                    EngineBindingRef(**pinned)
                )
                pinned["binding_version"] = str(binding.get("binding_version", pinned["binding_version"]))
                pinned["workflow_hash"] = workflow_hash
                pinned["binding_hash"] = binding_hash
            identities.append(pinned)
            continue

        per_module = modules_cfg.get(module_id) or {}
        fallback_version = str(engine_cfg.get("module_version", "v1")) if module_id == default_module else "v1"
        fallback_binding = str(engine_cfg.get("binding_version", "v1")) if module_id == default_module else "v1"
        identity: dict[str, str | None] = {
            "module_id": module_id,
            "module_version": str(per_module.get("module_version") or fallback_version),
            "provider": provider,
            "binding_version": str(per_module.get("binding_version") or fallback_binding),
            "workflow_hash": None,
            "binding_hash": None,
        }
        if provider == "comfyui":
            if adapter is None:
                from app.engine.comfyui import ComfyUIAdapter

                adapter = ComfyUIAdapter(engine_cfg.get("options") or {}, comfyui_config=settings.comfyui)
            actual_version, workflow_hash, binding_hash = adapter.binding_identity(
                module_id, identity["binding_version"]
            )
            identity["binding_version"] = actual_version
            identity["workflow_hash"] = workflow_hash
            identity["binding_hash"] = binding_hash
        identities.append(identity)
    return identities


def module_identity(settings: Settings) -> dict[str, str | None]:
    """兼容入口：默认（单模块）身份 = resolve_workflow_modules 的第一项。"""
    identities = resolve_workflow_modules(settings, None)
    return identities[0]


def _binding_unavailable_reason(error_type: str) -> str:
    if error_type == "BINDING_NOT_FOUND":
        return "binding_not_configured"
    if error_type in ("WORKFLOW_HASH_MISMATCH", "BINDING_HASH_MISMATCH", "BINDING_IDENTITY_MISMATCH"):
        return "binding_invalid"
    return "binding_unavailable"


def module_availability(settings: Settings) -> list[dict]:
    """每个已注册模块的**真实可执行性**（registered ≠ available；Phase 5.1 Task7 + Phase 6 Task5）。

    Phase 6 Task5 收紧：

    - `module_version` 与 `binding_version` 是不同域，**禁止互相 fallback**
      （旧实现把配置的 module_version 当作 binding_version 兜底）；
    - 新 Job 将使用的 module 代码版本必须真实注册（registry 校验），
      否则 available=false / module_version_not_registered（执行期必炸的问题提前暴露）；
    - comfyui：provider binding 能加载（目录存在 / 自描述一致 / 指纹）才 available；
    - mock：测试引擎可执行任何已注册模块 → available；
    - unbound：无引擎 → available=false（engine_not_configured）。

    只检查磁盘绑定，不探测引擎在线状态——ComfyUI 临时离线 ≠ 模块不存在，
    Engine 是否在线由 /engine/status 单独显示。
    前端"图片生成 Gate"只能依据 available=true 判断，禁止因为代码里注册了就显示可用。
    """
    from app.workflows.registry import default_registry

    engine_cfg = (settings.workflow.raw or {}).get("engine") or {}
    provider = str(engine_cfg.get("provider", "unbound"))
    modules_cfg = engine_cfg.get("modules") or {}
    default_module = str(engine_cfg.get("module_id", "basic_generate"))
    registry = default_registry()

    adapter = None
    result: list[dict] = []
    for module_id in registry.ids():
        per_module = modules_cfg.get(module_id) or {}
        is_default = module_id == default_module
        # Task5：两个版本字段各自回落（默认模块用 engine 级配置，其余模块假定 v1）
        module_version = str(per_module.get("module_version") or (
            str(engine_cfg.get("module_version", "v1")) if is_default else "v1"
        ))
        binding_version = str(per_module.get("binding_version") or (
            str(engine_cfg.get("binding_version", "v1")) if is_default else "v1"
        ))
        entry: dict = {
            "module_id": module_id,
            "registered": True,
            "module_version": module_version,
            "provider": provider,
            "binding_version": binding_version,
            "available": False,
            "unavailable_reason": None,
        }
        if not registry.has(module_id, module_version):
            entry["unavailable_reason"] = "module_version_not_registered"
            result.append(entry)
            continue
        if provider == "comfyui":
            if adapter is None:
                from app.engine.comfyui import ComfyUIAdapter

                adapter = ComfyUIAdapter(
                    engine_cfg.get("options") or {}, comfyui_config=settings.comfyui
                )
            try:
                actual_version, _workflow_hash, _binding_hash = adapter.binding_identity(
                    module_id, binding_version
                )
            except EngineError as error:
                entry["unavailable_reason"] = _binding_unavailable_reason(error.error_type)
            except Exception:  # noqa: BLE001 —— 任何加载异常都只能导致"不可用"，绝不 500
                entry["unavailable_reason"] = "binding_unavailable"
            else:
                entry["binding_version"] = actual_version
                entry["available"] = True
        elif provider == "mock":
            entry["available"] = True
        else:
            entry["unavailable_reason"] = "engine_not_configured"
        result.append(entry)
    return result