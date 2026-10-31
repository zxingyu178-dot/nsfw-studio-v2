"""Agent 提交的工作流解析与能力校验（W1.2-B）。

边界：
- 默认工作流只通过现有 ``resolve_workflow_modules(settings, [])`` 解析，
  不在本模块另写一套默认逻辑；
- 允许模块由 WorkflowModule capabilities 决定（is_generative / input_required /
  allowed_job_kinds），不做静态枚举；
- 只开放单生成模块 + 可选 upscale，不开放任意 Pipeline / 输入图片链路。
"""
from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.core.errors import ValidationError
from app.engine.base import EngineError
from app.engine.factory import module_availability, resolve_workflow_modules
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
    upscale: bool,
) -> list[dict[str, Any]]:
    """解析实际工作流身份：显式 module_id 或服务器默认，再按需追加 upscale。

    返回的是服务端解析出的真实身份列表（含 provider / binding_version / 双指纹），
    Agent 不传入、也不能伪造这些字段。
    """
    if module_id is not None and not str(module_id).strip():
        raise ValidationError(
            "module_id 不能为空字符串或纯空白；只有不传/null 才使用服务器默认",
            code="AGENT_MODULE_UNKNOWN",
            details={"module_id": module_id},
        )
    normalized_id = str(module_id).strip() if module_id is not None else None
    requested = [{"module_id": normalized_id}] if normalized_id else []
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
    if upscale and primary_id == "upscale":
        raise ValidationError(
            "Agent 只允许文生图工作流 + 可选高清放大，upscale 不能作为 Primary",
            code="AGENT_MODULE_NOT_TEXT_GENERATE",
            details={"module_id": primary_id},
        )
    planned = [{"module_id": primary_id}]
    if upscale:
        planned.append({"module_id": "upscale"})
    try:
        return resolve_workflow_modules(settings, planned)
    except EngineError as error:
        raise _translate(error, primary_id) from error


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
