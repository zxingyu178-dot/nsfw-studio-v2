"""W2.0 Runtime Guard — ComfyUI 任务提交前的动态运行条件检测。

只复用现有基础设施：
- ComfyUIAdapter.health()（/system_stats）
- ComfyUIAdapter.load_binding()（workflow.json + binding.yaml + 双 Hash）
- 现行 settings / resolve_workflow_modules 的真实执行身份

不新建第二套引擎管理或工作流注册体系；不下载模型、不安装节点、不修改 Binding。
检测状态统一为 READY / BLOCKED / UNKNOWN；UNKNOWN 不得当作 READY。
"""
from __future__ import annotations

import asyncio
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from app.core.config import Settings
from app.core.errors import ValidationError
from app.engine.base import EngineBindingRef, EngineError

STATUS_READY = "READY"
STATUS_BLOCKED = "BLOCKED"
STATUS_UNKNOWN = "UNKNOWN"

# ComfyUI 模型加载节点 → (文件名输入字段, 模型目录)
MODEL_LOADERS: dict[str, tuple[str, str]] = {
    "UnetLoaderGGUF": ("unet_name", "diffusion_models"),
    "UNETLoader": ("unet_name", "diffusion_models"),
    "CLIPLoader": ("clip_name", "text_encoders"),
    "VAELoader": ("vae_name", "vae"),
    "LoraLoader": ("lora_name", "loras"),
    "LoraLoaderModelOnly": ("lora_name", "loras"),
    "UpscaleModelLoader": ("model_name", "upscale_models"),
}
# binding.requirements.models.type → ComfyUI 模型目录
FOLDER_ALIASES = {
    "diffusion_models": "diffusion_models",
    "unet": "diffusion_models",
    "text_encoders": "text_encoders",
    "clip": "text_encoders",
    "vae": "vae",
    "loras": "loras",
    "upscale_models": "upscale_models",
}

SYSTEM_TTL_SECONDS = 30.0
NODE_TTL_SECONDS = 60.0
MODEL_TTL_SECONDS = 30.0

_SYSTEM_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_NODE_CACHE: dict[str, tuple[float, tuple[int, Any] | None]] = {}
_MODEL_CACHE: dict[str, tuple[float, tuple[int, Any] | None]] = {}
_DEPS_CACHE: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()


def reset_preflight_cache() -> None:
    """测试专用：清空进程内检测缓存。"""
    with _CACHE_LOCK:
        _SYSTEM_CACHE.clear()
        _NODE_CACHE.clear()
        _MODEL_CACHE.clear()
        _DEPS_CACHE.clear()


def _now() -> float:
    return time.monotonic()


def _cache_get(cache: dict, key, ttl: float) -> tuple[bool, Any]:
    with _CACHE_LOCK:
        entry = cache.get(key)
        if entry is None:
            return False, None
        stored_at, value = entry
        if _now() - stored_at > ttl:
            cache.pop(key, None)
            return False, None
        return True, value


def _cache_set(cache: dict, key, value) -> None:
    with _CACHE_LOCK:
        cache[key] = (_now(), value)


def _http_get_json(base_url: str, path: str, timeout: float = 5.0) -> tuple[int, Any] | None:
    """返回 (status_code, data)；网络异常/解析失败返回 None（调用方映射为 UNKNOWN）。"""
    try:
        with httpx.Client(trust_env=False, timeout=timeout) as client:
            response = client.get(f"{base_url}{path}")
            if response.status_code != 200:
                return response.status_code, None
            return response.status_code, response.json()
    except Exception:  # noqa: BLE001 —— 任何异常都只能代表“无法验证”
        return None


def _parse_version(value: str) -> tuple[int, ...] | None:
    match = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", value or "")
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def _node_inputs(node: Any) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    inputs = node.get("inputs")
    return inputs if isinstance(inputs, dict) else {}


def _extract_dependencies(
    workflow: dict[str, Any], binding: dict[str, Any]
) -> tuple[list[str], list[dict[str, str]], list[str]]:
    """从 workflow.json 自动解析：(节点 class_type 列表, 模型 [(folder, filename)], 未知 Loader 原因)。"""
    nodes = [node for node in workflow.values() if isinstance(node, dict)]
    classes = sorted({
        str(node.get("class_type"))
        for node in nodes
        if isinstance(node.get("class_type"), str) and node.get("class_type")
    })

    models: list[dict[str, str]] = []
    unknown: list[str] = []
    seen: set[tuple[str, str]] = set()

    def add_model(folder: str, filename: str) -> None:
        key = (folder, filename)
        if key and key not in seen:
            seen.add(key)
            models.append({"folder": folder, "filename": filename})

    requirements = binding.get("requirements") if isinstance(binding.get("requirements"), dict) else {}
    for item in requirements.get("models") or []:
        if not isinstance(item, dict) or not item.get("filename"):
            continue
        declared_type = str(item.get("type") or item.get("folder") or "")
        folder = FOLDER_ALIASES.get(declared_type)
        if folder is None:
            unknown.append(f"requirements.models 使用未知类型 {declared_type!r}（{item['filename']}）")
            continue
        add_model(folder, str(item["filename"]).replace("\\", "/").split("/")[-1])

    for node in nodes:
        class_type = str(node.get("class_type") or "")
        spec = MODEL_LOADERS.get(class_type)
        if spec is not None:
            field, folder = spec
            filename = _node_inputs(node).get(field)
            if isinstance(filename, str) and filename.strip():
                add_model(folder, filename.replace("\\", "/").split("/")[-1])
            continue
        # 未知模型加载节点：不允许静默判定 READY
        if "Loader" in class_type:
            unknown.append(f"未识别的模型加载节点 {class_type}，无法验证其模型依赖")
    return classes, models, unknown


class RuntimePreflightService:
    """一次检测：引擎 → Binding → 节点 → 模型 → 版本。"""

    def __init__(
        self,
        settings: Settings,
        adapter,
        *,
        http_get: Callable[[str, str, float], tuple[int, Any] | None] | None = None,
    ) -> None:
        self.settings = settings
        self.adapter = adapter
        self._http_get = http_get or _http_get_json

    # ===== provider / 引擎 =====
    def _provider(self) -> str:
        engine = (self.settings.workflow.raw or {}).get("engine") or {}
        return str(engine.get("provider") or "unbound")

    def _base_url(self) -> str:
        return str(getattr(self.adapter, "base_url", "") or "")

    def _health(self) -> tuple[dict[str, Any], bool]:
        url = self._base_url()
        cached, value = _cache_get(_SYSTEM_CACHE, url, SYSTEM_TTL_SECONDS)
        if cached:
            return value, True
        status = asyncio.run(self.adapter.health())
        data = {
            "online": bool(getattr(status, "online", False)),
            "name": str(getattr(status, "engine_name", "") or ""),
            "version": str(getattr(status, "engine_version", "") or ""),
            "detail": str(getattr(status, "detail", "") or ""),
        }
        _cache_set(_SYSTEM_CACHE, url, data)
        return data, False

    # ===== ComfyUI 动态探针 =====
    def _node_registered(self, class_type: str) -> tuple[bool, bool]:
        """返回 (是否注册, 结果可信)；请求失败 → 不可信。"""
        url = self._base_url()
        key = f"{url}|{class_type}"
        cached, value = _cache_get(_NODE_CACHE, key, NODE_TTL_SECONDS)
        if cached:
            return self._interpret_node(value)
        value = self._http_get(url, f"/object_info/{class_type}", 5.0)
        _cache_set(_NODE_CACHE, key, value)
        return self._interpret_node(value)

    @staticmethod
    def _interpret_node(value: tuple[int, Any] | None) -> tuple[bool, bool]:
        if value is None:
            return False, False
        status_code, data = value
        if status_code == 404:
            return False, True
        if status_code != 200:
            return False, False
        return (bool(data), True)

    def _models_in_folder(self, folder: str) -> tuple[list[str] | None, bool]:
        """返回 (文件名列表, 结果可信)。"""
        url = self._base_url()
        key = f"{url}|{folder}"
        cached, value = _cache_get(_MODEL_CACHE, key, MODEL_TTL_SECONDS)
        if cached:
            return self._interpret_models(value)
        value = self._http_get(url, f"/models/{folder}", 5.0)
        _cache_set(_MODEL_CACHE, key, value)
        return self._interpret_models(value)

    @staticmethod
    def _interpret_models(value: tuple[int, Any] | None) -> tuple[list[str] | None, bool]:
        if value is None:
            return None, False
        status_code, data = value
        if status_code != 200:
            return None, False
        if isinstance(data, list):
            return [str(item) for item in data], True
        if isinstance(data, dict):
            names = [str(item) for item in data.get("models", [])] if "models" in data else []
            return names, True
        return None, False

    # ===== 主检测 =====
    def check_modules(self, modules: list[dict[str, Any]]) -> dict[str, Any]:
        provider = self._provider()
        checked_at = datetime.now(timezone.utc).isoformat()

        if provider != "comfyui":
            status = STATUS_READY if provider == "mock" else STATUS_UNKNOWN
            module_results = [
                {
                    "module_id": module.get("module_id"),
                    "binding_version": module.get("binding_version"),
                    "workflow_hash": module.get("workflow_hash"),
                    "binding_hash": module.get("binding_hash"),
                    "status": status,
                    "missing_nodes": [],
                    "missing_models": [],
                    "missing_requirements": [],
                    "unknown_reasons": [] if status == STATUS_READY else ["engine_not_configured"],
                    "notes": ["mock engine：跳过真实依赖检测"] if provider == "mock" else [],
                    "cache_hit": False,
                }
                for module in modules
            ]
            return {
                "status": status,
                "engine": {
                    "online": provider == "mock",
                    "version": "mock" if provider == "mock" else "",
                    "detail": "mock engine" if provider == "mock" else "引擎未配置为 comfyui，无法动态检测",
                },
                "modules": module_results,
                "checked_at": checked_at,
                "cache_hit": False,
            }

        if self.adapter is None:
            return self._unknown_result(modules, "engine_adapter_missing", checked_at)

        health, health_cached = self._health()
        if not health["online"]:
            return self._unknown_result(
                modules, "engine_offline", checked_at,
                engine={"online": False, "version": health.get("version", ""), "detail": health.get("detail", "")},
            )

        engine_info = {
            "online": True,
            "version": health.get("version", ""),
            "detail": health.get("detail", ""),
        }
        results: list[dict[str, Any]] = []
        all_cached = health_cached
        for module in modules:
            result, module_cached = self._check_single(module, engine_info)
            results.append(result)
            all_cached = all_cached and module_cached

        if any(item["status"] == STATUS_BLOCKED for item in results):
            status = STATUS_BLOCKED
        elif any(item["status"] == STATUS_UNKNOWN for item in results):
            status = STATUS_UNKNOWN
        else:
            status = STATUS_READY
        return {
            "status": status,
            "engine": engine_info,
            "modules": results,
            "checked_at": checked_at,
            "cache_hit": all_cached,
        }

    def _unknown_result(
        self, modules: list[dict[str, Any]], reason: str, checked_at: str,
        *, engine: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "status": STATUS_UNKNOWN,
            "engine": engine or {"online": False, "version": "", "detail": reason},
            "modules": [
                {
                    "module_id": module.get("module_id"),
                    "binding_version": module.get("binding_version"),
                    "workflow_hash": module.get("workflow_hash"),
                    "binding_hash": module.get("binding_hash"),
                    "status": STATUS_UNKNOWN,
                    "missing_nodes": [],
                    "missing_models": [],
                    "missing_requirements": [],
                    "unknown_reasons": [reason],
                    "notes": [],
                    "cache_hit": False,
                }
                for module in modules
            ],
            "checked_at": checked_at,
            "cache_hit": False,
        }

    def _check_single(
        self, module: dict[str, Any], engine_info: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        module_id = str(module.get("module_id") or "")
        binding_version = str(module.get("binding_version") or "")
        base: dict[str, Any] = {
            "module_id": module_id,
            "binding_version": binding_version,
            "workflow_hash": module.get("workflow_hash"),
            "binding_hash": module.get("binding_hash"),
            "status": STATUS_READY,
            "missing_nodes": [],
            "missing_models": [],
            "missing_requirements": [],
            "unknown_reasons": [],
            "notes": [],
            "cache_hit": False,
        }
        ref = EngineBindingRef(
            module_id=module_id,
            module_version=str(module.get("module_version") or "v1"),
            provider="comfyui",
            binding_version=binding_version,
            workflow_hash=module.get("workflow_hash"),
            binding_hash=module.get("binding_hash"),
        )
        try:
            workflow, binding, workflow_hash, binding_hash = self.adapter.load_binding(ref)
        except EngineError as error:
            base.update(status=STATUS_UNKNOWN, unknown_reasons=[f"{error.error_type}: {error.message}"])
            return base, False

        base["workflow_hash"] = workflow_hash
        base["binding_hash"] = binding_hash
        deps_key = (module_id, workflow_hash, binding_hash)
        cached, deps = _cache_get(_DEPS_CACHE, deps_key, 86400.0)
        if cached:
            base["cache_hit"] = True
            parsed = deps
        else:
            classes, models, unknown_loaders = _extract_dependencies(workflow, binding)
            parsed = {"classes": classes, "models": models, "unknown_loaders": unknown_loaders}
            _cache_set(_DEPS_CACHE, deps_key, parsed)

        classes = list(parsed.get("classes") or [])
        models = list(parsed.get("models") or [])
        unknown_reasons = list(parsed.get("unknown_loaders") or [])

        for class_type in classes:
            registered, reliable = self._node_registered(class_type)
            if not reliable:
                unknown_reasons.append(f"节点 {class_type} 查询失败")
            elif not registered:
                base["missing_nodes"].append(class_type)

        folder_names: dict[str, list[str] | None] = {}
        for item in models:
            folder = str(item.get("folder") or "")
            filename = str(item.get("filename") or "")
            if folder not in folder_names:
                folder_names[folder], reliable = self._models_in_folder(folder)
                if not reliable:
                    unknown_reasons.append(f"模型目录 {folder} 查询失败")
            names = folder_names[folder]
            if names is None:
                continue
            if filename not in names:
                base["missing_models"].append({"folder": folder, "filename": filename})

        requirements = binding.get("requirements") if isinstance(binding.get("requirements"), dict) else {}
        min_version = str(requirements.get("comfyui_min_version") or "").strip()
        if min_version:
            current = _parse_version(str(engine_info.get("version") or ""))
            required = _parse_version(min_version)
            if required is None:
                unknown_reasons.append(f"无法解析 Binding 最低 ComfyUI 版本 {min_version!r}")
            elif current is None:
                unknown_reasons.append("无法解析当前 ComfyUI 版本，不能满足最低版本要求")
            elif current < required:
                base["missing_requirements"].append(
                    f"ComfyUI 版本不满足：需要 {min_version}，当前 {engine_info.get('version')}"
                )
        else:
            base["notes"].append("Binding 未声明 comfyui_min_version（按兼容政策不强制）")

        if base["missing_nodes"] or base["missing_models"] or base["missing_requirements"]:
            base["status"] = STATUS_BLOCKED
        elif unknown_reasons:
            base["status"] = STATUS_UNKNOWN
        else:
            base["status"] = STATUS_READY
        base["unknown_reasons"] = unknown_reasons
        return base, bool(base["cache_hit"])


def run_preflight(settings: Settings, adapter, modules: list[dict[str, Any]]) -> dict[str, Any]:
    """执行检测并在非 READY 时抛出统一业务错误（Job 创建门禁入口）。"""
    result = RuntimePreflightService(settings, adapter).check_modules(modules)
    ensure_preflight_ready(result)
    return result


def ensure_preflight_ready(result: dict[str, Any]) -> None:
    """Job 提交 Gate：READY 通过；BLOCKED / UNKNOWN 一律拒绝，不静默放行。"""
    status = result.get("status")
    if status == STATUS_READY:
        return
    details = result.get("modules") or []
    parts: list[str] = []
    for item in details:
        for node in item.get("missing_nodes") or []:
            parts.append(f"{item.get('module_id')}: 缺少节点 {node}")
        for model in item.get("missing_models") or []:
            parts.append(f"{item.get('module_id')}: 缺少模型 {model.get('folder')}/{model.get('filename')}")
        for reason in item.get("missing_requirements") or []:
            parts.append(f"{item.get('module_id')}: {reason}")
        for reason in item.get("unknown_reasons") or []:
            parts.append(f"{item.get('module_id')}: {reason}")
    detail_text = "；".join(parts) if parts else str(result.get("engine", {}).get("detail") or "无法验证运行环境")
    code = "RUNTIME_PREFLIGHT_BLOCKED" if status == STATUS_BLOCKED else "RUNTIME_PREFLIGHT_UNKNOWN"
    raise ValidationError(
        f"运行环境检测未通过（{status}）：{detail_text}",
        code=code,
        details=result,
    )
