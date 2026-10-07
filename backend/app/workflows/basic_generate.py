"""BasicGenerateModule — 第一套正式 WorkflowModule（Phase 2.1 规范 §三）。

职责（只做能力定义与标准输入/引擎请求的构造）：
- 声明模块身份、版本、参数；
- 把 PipelineExecutor 提供的通用 JobRequestContext 映射为模块标准输入 WorkflowInput；
- 把标准输入映射为 EngineJobRequest（参数名属于模块契约，不属于 Worker）。

本模块不包含任何具体引擎（ComfyUI）的地址、节点或 Workflow JSON 逻辑——
真正的引擎调用只发生在 EngineAdapter；具体注入位置在 provider binding。
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.engine.base import EngineAdapter, EngineError, EngineJobRequest
from app.workflows.base import (
    JobRequestContext,
    ModuleCapabilities,
    ParameterSpec,
    WorkflowInput,
    WorkflowModule,
    WorkflowOutput,
    WorkflowValidation,
)

SIZE_MIN = 64
SIZE_MAX = 4096
SEED_MAX = 2147483647


class BasicGenerateModule(WorkflowModule):
    """文生图基础模块：positive/negative/width/height/seed → EngineAdapter。"""

    module_id = "basic_generate"
    module_version = "v1"

    def __init__(self, poll_interval_seconds: float = 0.2) -> None:
        self._poll_interval = poll_interval_seconds

    # ===== 能力声明 =====
    def capabilities(self) -> ModuleCapabilities:
        return ModuleCapabilities(
            module_id=self.module_id,
            module_version=self.module_version,
            title="基础生成",
            description="标准文生图：Prompt / Negative / 尺寸 / Seed，经 EngineAdapter 执行",
            parameters=(
                ParameterSpec("positive_prompt", "string", required=True, description="最终正向 Prompt"),
                ParameterSpec("negative_prompt", "string", default="", description="负向 Prompt"),
                ParameterSpec("width", "int", default=1024, description=f"{SIZE_MIN}~{SIZE_MAX}"),
                ParameterSpec("height", "int", default=1024, description=f"{SIZE_MIN}~{SIZE_MAX}"),
                ParameterSpec("seed", "int", required=True, description=f"0~{SEED_MAX}（每张独立）"),
            ),
        )

    # ===== 标准输入 =====
    def build_input(self, context: JobRequestContext) -> WorkflowInput:
        """通用 Job 上下文 → 模块标准输入（模块独占的参数映射）。"""
        settings: dict[str, Any] = dict(context.generation_settings or {})
        return WorkflowInput(values={
            "positive_prompt": context.positive_prompt,
            "negative_prompt": context.negative_prompt,
            "width": int(settings.get("width", 1024)),
            "height": int(settings.get("height", 1024)),
            "seed": int(context.seed),
        })

    def validate_input(self, payload: WorkflowInput) -> WorkflowValidation:
        errors: list[str] = []
        values = payload.values
        for key in ("width", "height"):
            try:
                size = int(values.get(key, 1024))
            except (TypeError, ValueError):
                errors.append(f"{key} 必须为整数")
                continue
            if not SIZE_MIN <= size <= SIZE_MAX:
                errors.append(f"{key} 取值范围为 {SIZE_MIN}~{SIZE_MAX}")
        try:
            seed = int(values.get("seed", -1))
        except (TypeError, ValueError):
            errors.append("seed 必须为整数")
        else:
            if not 0 <= seed <= SEED_MAX:
                errors.append(f"seed 取值范围为 0~{SEED_MAX}")
        return WorkflowValidation(ok=not errors, errors=tuple(errors))

    # ===== 引擎请求（Worker 经 PipelineExecutor 调用） =====
    def build_engine_request(self, context: JobRequestContext) -> EngineJobRequest:
        payload = self.build_input(context)
        validation = self.validate_input(payload)
        if not validation.ok:
            raise EngineError("WORKFLOW_ERROR", f"模块输入校验失败: {'; '.join(validation.errors)}")
        return EngineJobRequest(
            job_type=self.module_id,
            parameters=dict(payload.values),
            metadata=dict(context.metadata or {}),
        )

    # ===== 完整执行（Pipeline 直跑路径；队列 Worker 用细粒度 API 保留暂停/取消语义） =====
    async def execute(self, payload: WorkflowInput, engine: EngineAdapter) -> WorkflowOutput:
        validation = self.validate_input(payload)
        if not validation.ok:
            raise EngineError("WORKFLOW_ERROR", f"模块输入校验失败: {'; '.join(validation.errors)}")

        engine_job_id = await engine.submit_job(
            EngineJobRequest(job_type=self.module_id, parameters=dict(payload.values))
        )
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
            # artifacts 只提供引用（文件名）；字节导入 DataRoot 由上层（Worker/Pipeline）完成
            artifacts={f"image_{index}": output.filename for index, output in enumerate(outputs)},
            metadata={
                "engine_job_id": engine_job_id,
                "module_id": self.module_id,
                "module_version": self.module_version,
            },
        )