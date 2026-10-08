"""Modules API：WorkflowModule 能力声明（Phase 5 §二十：前端模式判定，不硬编码模块列表）。"""
from __future__ import annotations

from fastapi import APIRouter

from app.workflows.registry import default_registry

router = APIRouter(prefix="/modules", tags=["modules"])


@router.get("", summary="已注册 WorkflowModule 能力列表（含输入/输出语义）")
def list_modules() -> list[dict]:
    """返回全部已注册模块的能力声明。

    前端"文生图 / 图片生成"模式判定（§二十）：图片生成需要存在
    ``input_required=true`` 且 ``output_kind=processed`` 的模块；
    Gate B 时列表中没有此类模块 → 显示"尚未配置可用工作流"。
    """
    registry = default_registry()
    result: list[dict] = []
    for module_id in registry.ids():
        capabilities = registry.get(module_id).capabilities()
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
        })
    return result