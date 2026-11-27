"""Agent 提交的工作流解析与能力校验（W1.2-B）。

边界：
- 默认工作流只通过现有 ``resolve_workflow_modules(settings, [])`` 解析，
  不在本模块另写一套默认逻辑；
- 允许模块由 WorkflowModule capabilities 决定（is_generative / input_required /
  allowed_job_kinds），不做静态枚举；
- 只开放单生成模块，不开放任意 Pipeline / 输入图片链路。
"""
from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.core.errors import ValidationError
from app.engine.base import EngineBindingRef, EngineError
from app.engine.factory import module_availability, resolve_workflow_modules
from app.schemas.job import snapshot_model
from app.services.workflow_registry_service import WorkflowRegistryService
from app.workflows.registry import default_registry

_BINDING_ERRORS = {
    "BINDING_NOT_FOUND",
    "WORKFLOW_HASH_MISMATCH",
    "BINDING_HASH_MISMATCH",
    "BINDING_IDENTITY_MISMATCH",
}


def _translate(error: EngineError, module_id: str | None) -> ValidationError:
    code = "AGENT_MODULE_UNAVAILABLE" if error.error_type in _BINDING_ERRORS else "AGENT_MODULE_UNKNOWN"
    return ValidationError(
        f"Agent 工作流不可用：{error.message}",
        code=code,
        details={"module_id": module_id},
    )


def resolve_agent_workflow_modules(
    settings: Settings,
    module_id: str | None,
    *,
    module_version: str | None = None,
    binding_version: str | None = None,
) -> list[dict[str, Any]]:
    """解析实际工作流身份：显式 module_id / 版本或服务器默认。

    - 不传版本：沿用服务器默认工作流；
    - 传 module_version / binding_version：必须同时有 module_id，按显式身份
      走既有 pinned 解析（仍由服务端校验 binding 指纹与放行状态）；
    - Agent 不能伪造 provider / workflow_hash / binding_hash。
    """
    if module_id is None and (module_version is not None or binding_version is not None):
        raise ValidationError(
            "指定 module_version / binding_version 时必须同时提供 module_id",
            code="AGENT_MODULE_UNKNOWN",
        )
    if module_id is not None and not str(module_id).strip():
        raise ValidationError(
            "module_id 不能为空字符串或纯空白；只有不传/null 才使用服务器默认",
            code="AGENT_MODULE_UNKNOWN",
            details={"module_id": module_id},
        )
    normalized_id = str(module_id).strip() if module_id is not None else None
    if not normalized_id:
        requested: list[dict[str, Any]] = []
    elif module_version is None and binding_version is None:
        requested = [{"module_id": normalized_id}]
    else:
        engine_cfg = (settings.workflow.raw or {}).get("engine") or {}
        provider = str(engine_cfg.get("provider", "unbound"))
        modules_cfg = engine_cfg.get("modules") or {}
        info = {
            item["module_id"]: item for item in module_availability(settings)
        }.get(normalized_id) or {}
        resolved_module_version = module_version or info.get("module_version")
        if not resolved_module_version:
            try:
                resolved_module_version = default_registry().get(normalized_id).module_version
            except EngineError as error:
                raise _translate(error, normalized_id) from error
        resolved_binding = (
            binding_version
            or info.get("binding_version")
            or (modules_cfg.get(normalized_id) or {}).get("binding_version")
        )
        if not resolved_binding:
            raise ValidationError(
                f"模块 {normalized_id} 没有可用的 binding_version",
                code="AGENT_MODULE_UNAVAILABLE",
                details={"module_id": normalized_id},
            )
        requested = [{
            "module_id": normalized_id,
            "module_version": str(resolved_module_version),
            "provider": provider,
            "binding_version": str(resolved_binding),
        }]
    try:
        primary = resolve_workflow_modules(settings, requested)[0]
    except EngineError as error:
        raise _translate(error, normalized_id) from error
    primary_id = str(primary.get("module_id") or "")
    if not primary_id or not default_registry().has(primary_id, primary.get("module_version")):
        raise ValidationError(
            f"未知工作流模块：{primary_id or module_id}",
            code="AGENT_MODULE_UNKNOWN",
            details={"module_id": module_id},
        )
    return [primary]


def resolve_default_checkpoint(settings: Settings, module: dict[str, Any]) -> str | None:
    """读取当前 binding 的默认底模（工作流注册中心 `default_parameters.model`）。"""
    try:
        manifest = WorkflowRegistryService(settings).get_workflow(
            str(module.get("module_id") or ""),
            str(module.get("binding_version") or ""),
        )
    except (KeyError, OSError, ValueError):
        return None
    default_model = (manifest.get("default_parameters") or {}).get("model")
    if isinstance(default_model, str) and default_model.strip():
        return default_model.strip()
    return None


def fill_default_checkpoint(settings: Settings, adapter: Any, modules: list[dict[str, Any]]) -> None:
    """模块未显式选底模时，把 binding 默认底模写入 config（统一 /jobs 与 /agent/jobs）。

    只补 provenance，不改执行语义（写入值与 binding 默认一致）：
    - 仅当该模块 binding 声明了 model 注入时才写，避免不支持的参数进入快照；
    - 适配器不支持 load_binding（如 mock）时跳过。
    """
    load_binding = getattr(adapter, "load_binding", None)
    if not callable(load_binding):
        return
    for module in modules:
        config = dict(module.get("config") or {})
        if config.get("model"):
            continue
        _workflow, binding, _workflow_hash, _binding_hash = load_binding(EngineBindingRef(
            module_id=str(module.get("module_id") or ""),
            module_version=str(module.get("module_version") or ""),
            provider=str(module.get("provider") or ""),
            binding_version=str(module.get("binding_version") or ""),
        ))
        if "model" not in (binding.get("inputs") or {}):
            continue
        default_model = resolve_default_checkpoint(settings, module)
        if default_model:
            config["model"] = default_model
            module["config"] = config


def job_status_payload(job: Any) -> dict[str, Any]:
    """Agent 轮询用的轻量任务进度：只读、稳定字段，避免每几秒拉完整 JobResponse。

    - progress = (已完成张数 + 当前张完成度) / 请求张数，保留 3 位小数；
    - current 仅在确有 RUNNING 张时出现；images 只列已完成且有产出的图；
    - model 与队列/手机/桌面详情同源（工作流快照，省略 model 的任务已由提交端补齐）。
    """
    items = sorted(job.items or [], key=lambda item: item.item_index)
    running = next((item for item in items if item.status == "RUNNING"), None)
    partial = float(running.progress) if running is not None and running.progress is not None else 0.0
    progress = (
        min(1.0, round((job.completed_count + partial) / job.requested_count, 3))
        if job.requested_count else None
    )
    return {
        "job_id": job.id,
        "status": job.status,
        "source": job.source,
        "module_id": job.module_id,
        "model": snapshot_model(job.workflow_snapshot_json),
        "requested_count": job.requested_count,
        "completed_count": job.completed_count,
        "failed_count": sum(1 for item in items if item.status == "FAILED"),
        "progress": progress,
        "current": {
            "item_index": running.item_index,
            "progress": float(running.progress) if running.progress is not None else None,
            "stage": running.current_stage,
            "seed": running.seed,
        } if running is not None else None,
        "queue_position": job.queue_position if job.status == "QUEUED" else None,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "error_type": job.error_type,
        "error_message": job.error_message,
        "images": [
            {"image_id": item.image_id, "seed": item.seed, "item_index": item.item_index}
            for item in items
            if item.status == "COMPLETED" and item.image_id
        ],
    }


def validate_agent_primary(settings: Settings, modules: list[dict[str, Any]]) -> None:
    """校验 Primary 是否允许 Agent 使用（在正式放行检查之后调用）。

    要求：已注册 + available + is_generative + 无输入图 + allowed_job_kinds 含 generate。
    """
    if not modules:
        raise ValidationError("Agent 请求缺少工作流模块", code="AGENT_MODULE_UNKNOWN")
    module = modules[0]
    module_id = str(module.get("module_id") or "")
    info = {item["module_id"]: item for item in module_availability(settings)}.get(module_id) or {}
    if not info or info.get("registered") is not True:
        raise ValidationError(
            f"未知工作流模块：{module_id}",
            code="AGENT_MODULE_UNKNOWN",
            details={"module_id": module_id},
        )
    if info.get("available") is not True:
        raise ValidationError(
            f"工作流当前不可用：{module_id}（{info.get('unavailable_reason') or 'binding 不可用'}）",
            code="AGENT_MODULE_UNAVAILABLE",
            details={"module_id": module_id, "reason": info.get("unavailable_reason")},
        )
    version = str(info.get("module_version") or module.get("module_version") or "v1")
    try:
        capabilities = default_registry().get(module_id, version).capabilities()
    except EngineError as error:
        raise _translate(error, module_id) from error
    if (
        capabilities.is_generative is not True
        or capabilities.input_required is True
        or "generate" not in tuple(capabilities.allowed_job_kinds)
    ):
        raise ValidationError(
            f"Agent 只允许无输入图片的文生图工作流，{module_id} 不符合"
            f"（is_generative={capabilities.is_generative}, "
            f"input_required={capabilities.input_required}, "
            f"allowed_job_kinds={list(capabilities.allowed_job_kinds)}）",
            code="AGENT_MODULE_NOT_TEXT_GENERATE",
            details={
                "module_id": module_id,
                "is_generative": capabilities.is_generative,
                "input_required": capabilities.input_required,
                "allowed_job_kinds": list(capabilities.allowed_job_kinds),
            },
        )
