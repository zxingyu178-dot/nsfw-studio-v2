"""Modules API：WorkflowModule 能力声明 + 真实可用性（Phase 5 §二十；Phase 5.1 Task7）。

前端"文生图 / 图片生成"模式判定与 Gate **只能依据本接口**：
- 能力字段（input_required / output_kind / …）来自 ModuleCapabilities；
- ``available`` 来自真实 provider binding 可执行性（registered ≠ available）；
  未配置 binding 的模块必须显示"不可用"，禁止因为代码注册了就显示可用。
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.config import Settings
from app.engine.factory import module_availability
from app.workflows.registry import default_registry

router = APIRouter(prefix="/modules", tags=["modules"])


@router.get("", summary="已注册 WorkflowModule 能力列表 + 真实可用性")
def list_modules(request: Request) -> list[dict]:
    """返回全部已注册模块的能力声明与可用性。

    响应字段（Phase 5.1 Task7）：
        module_id / module_version / title / description / 能力字段…
        registered（恒为 true——来自注册表）
        available（真实可执行：comfyui 下必须能加载 provider binding）
        provider / binding_version / unavailable_reason
    """
    settings: Settings = request.app.state.settings
    availability = {item["module_id"]: item for item in module_availability(settings)}

    registry = default_registry()
    result: list[dict] = []
    for module_id in registry.ids():
        capabilities = registry.get(module_id).capabilities()
        info = availability.get(module_id) or {}
        result.append({
            "module_id": capabilities.module_id,
            "module_version": capabilities.module_version,
            "title": capabilities.title,
            "description": capabilities.description,
            "uses_seed": capabilities.uses_seed,
            "input_kind": capabilities.input_kind,
            "input_required": capabilities.input_required,
            "input_role": capabilities.input_role,
            "output_kind": capabilities.output_kind,
            "parent_policy": capabilities.parent_policy,
            "output_cardinality": capabilities.output_cardinality,
            # Task7：真实可用性（前端 Gate 的唯一依据）
            "registered": True,
            "available": bool(info.get("available")),
            "provider": info.get("provider"),
            "binding_version": info.get("binding_version"),
            "unavailable_reason": info.get("unavailable_reason"),
        })
    return result