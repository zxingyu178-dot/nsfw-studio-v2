"""Modules API：WorkflowModule 能力声明 + 真实可用性（Phase 5 §二十；Phase 5.1 Task7）。

前端"文生图 / 图片生成"模式判定与 Gate **只能依据本接口**：
- 能力字段（input_required / output_kind / …）来自 ModuleCapabilities；
- ``available`` 来自真实 provider binding 可执行性（registered ≠ available）；
  未配置 binding 的模块必须显示"不可用"，禁止因为代码注册了就显示可用；
- Phase 7 Task8：capabilities 必须按**实际选中的 module_version** 获取
  （新 Job 将使用的版本 = availability 解析的配置版本），不能只拿注册表默认版本。
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.config import Settings
from app.engine.base import EngineError
from app.engine.factory import module_availability
from app.workflows.registry import default_registry

router = APIRouter(prefix="/modules", tags=["modules"])


@router.get("", summary="已注册 WorkflowModule 能力列表 + 真实可用性")
def list_modules(request: Request) -> list[dict]:
    """返回全部已注册模块的能力声明与可用性。

    响应字段（Phase 5.1 Task7；Phase 6 Task5/Task8/Task9；Phase 7 Task2/Task8）：
        module_id / module_version（新 Job 将使用的代码版本，已校验真实注册）
        title / description / 能力字段（含 size_mode / allowed_job_kinds /
        can_start_from_image / is_generative）/ parameters（ParameterSpec 元数据）…
        registered（module_id 已注册；版本级问题由 unavailable_reason 表达）
        available（真实可执行：版本已注册 + comfyui provider binding 可加载）
        provider / binding_version / unavailable_reason
    """
    settings: Settings = request.app.state.settings
    availability = {item["module_id"]: item for item in module_availability(settings)}

    registry = default_registry()
    result: list[dict] = []
    for module_id in registry.ids():
        info = availability.get(module_id) or {}
        selected_version = str(info.get("module_version") or "")
        # Task8（Phase 7）：按实际选中的 module_version 取能力声明；
        # 版本未注册（availability 已表达原因）时回落到默认版本实例（仅信息展示，Gate 看 available）。
        capabilities = None
        if selected_version:
            try:
                capabilities = registry.get(module_id, selected_version).capabilities()
            except EngineError:
                capabilities = None
        if capabilities is None:
            capabilities = registry.get(module_id).capabilities()
        result.append({
            "module_id": capabilities.module_id,
            # Task5（Phase 6）：新 Job 将使用的代码版本（availability 已校验真实注册）
            "module_version": selected_version or capabilities.module_version,
            "title": capabilities.title,
            "description": capabilities.description,
            "uses_seed": capabilities.uses_seed,
            "input_kind": capabilities.input_kind,
            "input_required": capabilities.input_required,
            "input_role": capabilities.input_role,
            "output_kind": capabilities.output_kind,
            "parent_policy": capabilities.parent_policy,
            "output_cardinality": capabilities.output_cardinality,
            # Phase 6 Task9：尺寸语义（explicit | input）——UI 据此决定是否显示显式宽高
            "size_mode": capabilities.size_mode,
            # Phase 7 Task2/Task8：能力驱动的 Job 类型许可与生成语义
            "allowed_job_kinds": list(capabilities.allowed_job_kinds),
            "can_start_from_image": capabilities.can_start_from_image,
            "is_generative": capabilities.is_generative,
            # Phase 6 Task8：参数元数据（前端按 type/min/max/step/enum_values 渲染控件，
            # 不再为每个模块手写 SettingsPane；configurable=true 才写入 WorkflowModuleRef.config）
            "parameters": [
                {
                    "name": spec.name,
                    "type": spec.type,
                    "required": spec.required,
                    "default": spec.default,
                    "title": spec.title,
                    "min": spec.min,
                    "max": spec.max,
                    "step": spec.step,
                    "enum_values": list(spec.enum_values),
                    "configurable": spec.configurable,
                    "description": spec.description,
                }
                for spec in capabilities.parameters
            ],
            # Task7/Task5（Phase 6）：真实可用性（前端 Gate 的唯一依据）
            "registered": bool(info.get("registered", True)),
            "available": bool(info.get("available")),
            "provider": info.get("provider"),
            "binding_version": info.get("binding_version"),
            "unavailable_reason": info.get("unavailable_reason"),
        })
    return result