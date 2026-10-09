"""UpscaleModule — 第二套正式 WorkflowModule（Phase 3 §十一/§十二）。

- 标准输入核心只有 input_image（外加少量模块参数），**禁止**知道 ComfyUI Node ID；
- prepare_inputs：把输入图片经 EngineAdapter 上传到引擎侧（§十三，Studio 唯一命名 +
  独立 subfolder），返回的引擎侧引用名由 build_engine_request 注入 provider binding；
- 高清 Image 的 kind=upscaled / parent_image_id 由 Worker/ImageService 在导入时落库（§十四）。

真实高清工作流选择见 docs/UPSCALE_WORKFLOW_INVENTORY.md
（本机已能稳定工作的 4x-UltraSharp 链，不下载新模型、不安装新节点）。
"""
from __future__ import annotations

import asyncio
from typing import Any, Mapping

from app.engine.base import EngineAdapter, EngineBindingRef, EngineError, EngineJobRequest
from app.workflows.base import (
    InputImageRef,
    JobRequestContext,
    ModuleCapabilities,
    ParameterSpec,
    WorkflowInput,
    WorkflowModule,
    WorkflowOutput,
    WorkflowValidation,
)


def _default_binding(module: "UpscaleModule") -> EngineBindingRef:
    return EngineBindingRef(
        module_id=module.module_id,
        module_version=module.module_version,
        provider="unbound",
        binding_version="v1",
    )


class UpscaleModule(WorkflowModule):
    """高清放大模块：已有图片 → 放大链 → 高清 Image（跨图库单张 / 生成流水线 Stage 2 共用）。"""

    module_id = "upscale"
    module_version = "v1"

    def __init__(self, poll_interval_seconds: float = 0.2) -> None:
        self._poll_interval = poll_interval_seconds

    # ===== 能力声明 =====
    def capabilities(self) -> ModuleCapabilities:
        return ModuleCapabilities(
            module_id=self.module_id,
            module_version=self.module_version,
            title="高清放大",
            description="已有图片 → 4x 高清放大（provider binding 决定实际放大链）",
            parameters=(
                ParameterSpec("input_image", "image", required=True, description="待放大的输入图片"),
            ),
            # Task2 输入/输出语义：放大链不使用随机 Seed；输出 kind=upscaled 且必须挂到输入图片下
            uses_seed=False,
            input_kind="image",
            input_required=True,
            input_role="source",
            output_kind="upscaled",
            parent_policy="input_image",
            output_cardinality=1,
            # Phase 6 Task9：输出尺寸跟随输入图片（×N 由 provider binding 决定，不是工作台宽高）
            size_mode="input",
        )

    # ===== 标准输入 =====
    def build_input(self, context: JobRequestContext) -> WorkflowInput:
        return WorkflowInput(values={"input_image": context.input_image})

    def validate_input(self, payload: WorkflowInput) -> WorkflowValidation:
        image = payload.values.get("input_image")
        errors: list[str] = []
        if not isinstance(image, InputImageRef):
            errors.append("input_image 必须为 InputImageRef（已有图片）")
        return WorkflowValidation(ok=not errors, errors=tuple(errors))

    # ===== 引擎侧输入准备（§十三：上传到引擎，仅使用 Studio 唯一命名） =====
    async def prepare_inputs(self, context: JobRequestContext,
                             engine: EngineAdapter) -> Mapping[str, Any]:
        image = context.input_image
        if image is None:
            raise EngineError("WORKFLOW_ERROR", "upscale 需要输入图片（input_image）")
        # Task4：输入图片走 EngineAdapter 正式契约（绝不是 getattr duck typing）；
        # 不支持的引擎由基类默认实现返回 ENGINE_INPUT_UNSUPPORTED（系统性、不重试）。
        engine_name = await engine.upload_input_image(
            image_id=image.image_id, file_name=image.file_name, data=image.data,
        )
        return {"input_image_name": engine_name}

    # ===== 引擎请求 =====
    def build_engine_request(self, context: JobRequestContext,
                             prepared: Mapping[str, Any] | None = None) -> EngineJobRequest:
        prepared = prepared or {}
        engine_name = prepared.get("input_image_name")
        if not engine_name:
            raise EngineError("WORKFLOW_ERROR", "upscale 输入图片未准备（prepared.input_image_name）")
        return EngineJobRequest(
            binding=context.binding or _default_binding(self),
            parameters={"input_image": engine_name},
            metadata=dict(context.metadata or {}),
        )

    # ===== 完整执行（Pipeline 直跑路径；队列 Worker 用细粒度 API 保留暂停/取消语义） =====
    async def execute(self, payload: WorkflowInput, engine: EngineAdapter,
                      *, binding: EngineBindingRef | None = None) -> WorkflowOutput:
        validation = self.validate_input(payload)
        if not validation.ok:
            raise EngineError("WORKFLOW_ERROR", f"模块输入校验失败: {'; '.join(validation.errors)}")

        context = JobRequestContext(
            input_image=payload.values.get("input_image"),
            binding=binding or _default_binding(self),
        )
        prepared = await self.prepare_inputs(context, engine)
        engine_job_id = await engine.submit_job(self.build_engine_request(context, prepared))
        while True:
            status = await engine.get_job_status(engine_job_id)
            if status.state == "succeeded":
                break
            if status.state == "failed":
                raise EngineError(status.error_type or "UNKNOWN_ENGINE_ERROR",
                                  status.message or "引擎执行失败")
            if status.state in ("canceled", "unknown"):
                raise EngineError("UNKNOWN_ENGINE_ERROR", f"引擎任务不可继续: {status.state}")
            await asyncio.sleep(self._poll_interval)

        outputs = await engine.get_job_outputs(engine_job_id)
        if not outputs:
            raise EngineError("OUTPUT_MISSING", "引擎报告成功但没有输出文件")
        return WorkflowOutput(
            artifacts={f"image_{index}": output.filename for index, output in enumerate(outputs)},
            metadata={
                "engine_job_id": engine_job_id,
                "module_id": self.module_id,
                "module_version": self.module_version,
            },
        )