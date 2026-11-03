"""测试替身：最小处理型 WorkflowModule（原 upscale 契约形状）。

产品已下线 4x 高清放大模块；仍需要验证「处理型 Stage / process Job」通用契约的
测试统一使用本替身：同样的 input_required、output_kind=upscaled、parent_policy=input_image
语义，但 module_id 为 fake_process，不会出现在产品默认注册表。
"""
from __future__ import annotations

from typing import Any, Mapping

from app.engine.base import EngineAdapter, EngineBindingRef, EngineError, EngineJobRequest
from app.workflows.base import (
    InputImageRef,
    InputSlotSpec,
    JobRequestContext,
    ModuleCapabilities,
    ParameterSpec,
    WorkflowInput,
    WorkflowModule,
    WorkflowOutput,
    WorkflowValidation,
)


def _default_binding(module: "FakeProcessModule") -> EngineBindingRef:
    return EngineBindingRef(
        module_id=module.module_id,
        module_version=module.module_version,
        provider="unbound",
        binding_version="v1",
    )


class FakeProcessModule(WorkflowModule):
    module_id = "fake_process"
    module_version = "v1"

    def capabilities(self) -> ModuleCapabilities:
        return ModuleCapabilities(
            module_id=self.module_id,
            module_version=self.module_version,
            title="处理型测试替身",
            description="已有图片 → 处理（仅用于测试通用处理型模块契约）",
            parameters=(
                ParameterSpec("input_image", "image", required=True, description="待处理的输入图片"),
            ),
            uses_seed=False,
            input_kind="image",
            input_required=True,
            input_role="source",
            output_kind="upscaled",
            parent_policy="input_image",
            output_cardinality=1,
            size_mode="input",
            allowed_job_kinds=("generate", "process"),
            can_start_from_image=True,
            is_generative=False,
            input_slots=(
                InputSlotSpec("source", required=True, max_count=1, description="待处理的输入图片"),
            ),
        )

    def build_input(self, context: JobRequestContext) -> WorkflowInput:
        return WorkflowInput(values={"input_image": context.input_image})

    def validate_input(self, payload: WorkflowInput) -> WorkflowValidation:
        image = payload.values.get("input_image")
        if not isinstance(image, InputImageRef):
            return WorkflowValidation(ok=False, errors=("input_image 必须为 InputImageRef（已有图片）",))
        return WorkflowValidation(ok=True)

    async def prepare_inputs(self, context: JobRequestContext,
                             engine: EngineAdapter) -> Mapping[str, Any]:
        image = context.input_image
        if image is None:
            raise EngineError("WORKFLOW_ERROR", "fake_process 需要输入图片（input_image）")
        engine_name = await engine.upload_input_image(
            image_id=image.image_id, file_name=image.file_name, data=image.data,
        )
        return {"input_image_name": engine_name}

    def build_engine_request(self, context: JobRequestContext,
                             prepared: Mapping[str, Any] | None = None) -> EngineJobRequest:
        prepared = prepared or {}
        engine_name = prepared.get("input_image_name")
        if not engine_name:
            raise EngineError("WORKFLOW_ERROR", "fake_process 输入图片未准备（prepared.input_image_name）")
        return EngineJobRequest(
            binding=context.binding or _default_binding(self),
            parameters={"input_image": engine_name},
            metadata=dict(context.metadata or {}),
        )

    async def execute(self, payload: WorkflowInput, engine: EngineAdapter,
                      *, binding: EngineBindingRef | None = None) -> WorkflowOutput:
        raise NotImplementedError
