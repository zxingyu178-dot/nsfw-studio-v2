"""EngineAdapter 工厂 + Workflow 模块身份解析。

- 按 configs 选择引擎实现（不修改核心）；
- Phase 3 §五：Job 创建时把请求的 workflow_modules 解析为**真实身份列表**
  （module/provider/binding_version/workflow_hash），作为 Pipeline 的唯一执行真源。
"""
from __future__ import annotations

from app.core.config import Settings
from app.engine.base import EngineAdapter

# 已知模块的固定执行顺序（基础生成 → 高清 → 未来模块按请求顺序追加）
MODULE_ORDER = ("basic_generate", "upscale")


def create_engine_adapter(settings: Settings) -> EngineAdapter:
    engine_cfg = (settings.workflow.raw or {}).get("engine") or {}
    provider = engine_cfg.get("provider", "unbound")
    options = engine_cfg.get("options") or {}

    if provider == "mock":
        from app.engine.mock import MockEngineAdapter

        return MockEngineAdapter(options)
    if provider == "comfyui":
        from app.engine.comfyui import ComfyUIAdapter

        # §0.2：Adapter 不再携带实例级 binding；身份来自每次 EngineJobRequest
        return ComfyUIAdapter(options, comfyui_config=settings.comfyui)
    from app.engine.unbound import UnboundEngineAdapter

    return UnboundEngineAdapter()


def resolve_workflow_modules(settings: Settings, requested: list[dict] | None) -> list[dict]:
    """请求的模块列表 → 真实身份列表（§五；默认仅基础生成）。

    每项输出 {module_id, module_version, provider, binding_version, workflow_hash}；
    comfyui 时从 provider binding 读取真实 binding_version 与 workflow_hash——
    以后 Workflow 被修改（必须新建版本目录）仍能追溯老 Job 当时的版本。
    """
    engine_cfg = (settings.workflow.raw or {}).get("engine") or {}
    provider = str(engine_cfg.get("provider", "unbound"))
    modules_cfg = engine_cfg.get("modules") or {}
    default_module = str(engine_cfg.get("module_id", "basic_generate"))

    ids: list[str] = []
    for entry in requested or []:
        module_id = str((entry or {}).get("module_id") or "").strip()
        if module_id and module_id not in ids:
            ids.append(module_id)
    if not ids:
        ids = [default_module]
    ordered = [module_id for module_id in MODULE_ORDER if module_id in ids]
    ordered += [module_id for module_id in ids if module_id not in MODULE_ORDER]

    identities: list[dict] = []
    adapter = None
    for module_id in ordered:
        per_module = modules_cfg.get(module_id) or {}
        fallback_version = str(engine_cfg.get("module_version", "v1")) if module_id == default_module else "v1"
        fallback_binding = str(engine_cfg.get("binding_version", "v1")) if module_id == default_module else "v1"
        identity: dict[str, str | None] = {
            "module_id": module_id,
            "module_version": str(per_module.get("module_version") or fallback_version),
            "provider": provider,
            "binding_version": str(per_module.get("binding_version") or fallback_binding),
            "workflow_hash": None,
        }
        if provider == "comfyui":
            if adapter is None:
                from app.engine.comfyui import ComfyUIAdapter

                adapter = ComfyUIAdapter(engine_cfg.get("options") or {}, comfyui_config=settings.comfyui)
            actual_version, workflow_hash = adapter.binding_identity(module_id, identity["binding_version"])
            identity["binding_version"] = actual_version
            identity["workflow_hash"] = workflow_hash
        identities.append(identity)
    return identities


def module_identity(settings: Settings) -> dict[str, str | None]:
    """兼容入口：默认（单模块）身份 = resolve_workflow_modules 的第一项。"""
    identities = resolve_workflow_modules(settings, None)
    return identities[0]