"""Img2ImgModule — 第三套正式 WorkflowModule（Phase 5.1 Gate C 成功路径）。

- 输入图片经 EngineAdapter.upload_input_image 正式契约上传（同 UpscaleModule §十三）；
- 标准输入：input_image + Prompt/Negative + Seed + denoise（模块参数唯一来源 = JobStage.config_json，
  由 PipelineExecutor 注入 JobRequestContext.module_config）；
- 输出 kind=processed / parent_policy=input_image / seed 进入 StageItem（由通用层落库）；
- **核心执行逻辑零改动**：QueueWorker / PipelineScheduler / ImageService 不因本模块增加而修改。

Provider binding：workflows/providers/comfyui/img2img/v1/（Qwen-Image 2.1 零下载 latent Img2Img，
来源见 docs/evidence/phase51-img2img/ 实验与 docs/PHASE51_REPORT.md）。
"""
from __future__ import annotations

import asyncio
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

DENOISE_MIN = 0.05
DENOISE_MAX = 1.0
# Phase 6 Task10 实测调整：0.55 在真实照片上近乎不变（精修档）；
# 0.8 在真实人像上人物保留良好且场景级 Prompt 明显生效 → 默认 0.8。
DEFAULT_DENOISE = 0.8
SEED_MAX = 2147483647


def _default_binding(module: "Img2ImgModule") -> EngineBindingRef:
    return EngineBindingRef(
        module_id=module.module_id,
        module_version=module.module_version,
        provider="unbound",
        binding_version="v1",
    )


def _coerce_denoise(raw: Any) -> float | None:
    if raw is None:
        return DEFAULT_DENOISE
    if isinstance(raw, bool):  # JSON true/false 不是合法的变化强度
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value


class Img2ImgModule(WorkflowModule):
    """图生图模块：已有图片 + Prompt → 新图（输出挂到输入图下，kind=processed）。"""

    module_id = "img2img"
    module_version = "v1"

    def __init__(self, poll_interval_seconds: float = 0.2) -> None:
        self._poll_interval = poll_interval_seconds

    # ===== 能力声明 =====
    def capabilities(self) -> ModuleCapabilities:
        return ModuleCapabilities(
            module_id=self.module_id,
            module_version=self.module_version,
            title="图生图",
            description="已有图片 + Prompt → 图生图（provider binding 决定实际链，denoise 控制变化强度）",
            parameters=(
                ParameterSpec("input_image", "image", required=True, description="输入图片（来源）"),
                ParameterSpec(
                    "denoise", "float", default=DEFAULT_DENOISE,
                    min=DENOISE_MIN, max=DENOISE_MAX, step=0.05, configurable=True,
                    title="变化强度",
                    description="0.55 以下≈精修（近乎不变）；0.8（默认）可做场景级变化；输出尺寸跟随输入图",
                ),
                ParameterSpec("positive_prompt", "string", required=True),
                ParameterSpec("negative_prompt", "string", default=""),
                ParameterSpec("seed", "int", required=True, description=f"0~{SEED_MAX}（每张独立）"),
            ),
            uses_seed=True,
            input_kind="image",
            input_required=True,
            input_role="source",
            output_kind="processed",
            parent_policy="input_image",
            output_cardinality=1,
            # Phase 6 Task9：输出尺寸 = 输入图尺寸（UI/详情显示"跟随输入图"，不展示假宽高）
            size_mode="input",
            # Phase 7 Task2/Task8：图生图可从已有图片起步（生成流水线 Stage0），
            # 是生成型模块（产出构成生成上下文锚点）；当前不允许处理型 Job
            allowed_job_kinds=("generate",),
            can_start_from_image=True,
            is_generative=True,
            # Phase 7 Task5：输入 Slot 契约——img2img 只消费 source（旧行为兼容）
            input_slots=(
                InputSlotSpec("source", required=True, max_count=1,
                              description="图生图输入（来源图片，来自 Studio 图库）"),
            ),
        )

    # ===== config（模块参数唯一事实源） =====
    def validate_config(self, config: Mapping[str, Any]) -> WorkflowValidation:
        errors: list[str] = []
        unknown = set(config.keys()) - {"denoise"}
        if unknown:
            errors.append(f"未知配置项: {', '.join(sorted(unknown))}")
        denoise = _coerce_denoise(config.get("denoise"))
        if denoise is None:
            errors.append("denoise 必须为数字")
        elif not DENOISE_MIN <= denoise <= DENOISE_MAX:
            errors.append(f"denoise 取值范围为 {DENOISE_MIN}~{DENOISE_MAX}")
        return WorkflowValidation(ok=not errors, errors=tuple(errors))

    # ===== 标准输入 =====
    def build_input(self, context: JobRequestContext) -> WorkflowInput:
        image = context.input_image
        if not isinstance(image, InputImageRef):
            raise EngineError("WORKFLOW_ERROR", "img2img 需要输入图片（input_image）")
        if context.seed is None:
            raise EngineError("WORKFLOW_ERROR", "img2img 需要 Seed（uses_seed=true）")
        denoise = _coerce_denoise(context.module_config.get("denoise"))
        if denoise is None:
            raise EngineError("WORKFLOW_ERROR", "img2img denoise 必须为数字")
        return WorkflowInput(values={
            "input_image": image,
            "positive_prompt": context.positive_prompt,
            "negative_prompt": context.negative_prompt,
            "seed": int(context.seed),
            "denoise": denoise,
        })

    def validate_input(self, payload: WorkflowInput) -> WorkflowValidation:
        errors: list[str] = []
        if not isinstance(payload.values.get("input_image"), InputImageRef):
            errors.append("input_image 必须为 InputImageRef（已有图片）")
        try:
            seed = int(payload.values.get("seed", -1))
        except (TypeError, ValueError):
            errors.append("seed 必须为整数")
        else:
            if not 0 <= seed <= SEED_MAX:
                errors.append(f"seed 取值范围为 0~{SEED_MAX}")
        denoise = payload.values.get("denoise")
        if denoise is not None and not (DENOISE_MIN <= float(denoise) <= DENOISE_MAX):
            errors.append(f"denoise 取值范围为 {DENOISE_MIN}~{DENOISE_MAX}")
        return WorkflowValidation(ok=not errors, errors=tuple(errors))

    # ===== 引擎侧输入准备（§十三：上传到引擎，仅使用 Studio 唯一命名） =====
    async def prepare_inputs(self, context: JobRequestContext,
                             engine: EngineAdapter) -> Mapping[str, Any]:
        image = context.input_image
        if image is None:
            raise EngineError("WORKFLOW_ERROR", "img2img 需要输入图片（input_image）")
        engine_name = await engine.upload_input_image(
            image_id=image.image_id, file_name=image.file_name, data=image.data,
        )
        return {"input_image_name": engine_name}

    # ===== 引擎请求 =====
    def build_engine_request(self, context: JobRequestContext,
                             prepared: Mapping[str, Any] | None = None) -> EngineJobRequest:
        payload = self.build_input(context)
        validation = self.validate_input(payload)
        if not validation.ok:
            raise EngineError("WORKFLOW_ERROR", f"模块输入校验失败: {'; '.join(validation.errors)}")
        prepared = prepared or {}
        engine_name = prepared.get("input_image_name")
        if not engine_name:
            raise EngineError("WORKFLOW_ERROR", "img2img 输入图片未准备（prepared.input_image_name）")
        parameters = {
            "input_image": engine_name,
            "positive_prompt": payload.values["positive_prompt"],
            "negative_prompt": payload.values["negative_prompt"],
            "seed": payload.values["seed"],
            "denoise": payload.values["denoise"],
        }
        return EngineJobRequest(
            binding=context.binding or _default_binding(self),
            parameters=parameters,
            metadata=dict(context.metadata or {}),
        )

    # ===== 完整执行（Pipeline 直跑路径；队列 Worker 用细粒度 API 保留暂停/取消语义） =====
    async def execute(self, payload: WorkflowInput, engine: EngineAdapter,
                      *, binding: EngineBindingRef | None = None) -> WorkflowOutput:
        validation = self.validate_input(payload)
        if not validation.ok:
            raise EngineError("WORKFLOW_ERROR", f"模块输入校验失败: {'; '.join(validation.errors)}")

        # Phase 6 Task6：payload 的 Prompt 必须完整进入 JobRequestContext，
        # 否则独立走 execute 时会提交空 Prompt（Worker 主链不经过这里，但公共抽象必须正确）
        context = JobRequestContext(
            input_image=payload.values.get("input_image"),
            positive_prompt=str(payload.values.get("positive_prompt") or ""),
            negative_prompt=str(payload.values.get("negative_prompt") or ""),
            seed=int(payload.values["seed"]),
            module_config={"denoise": payload.values.get("denoise")},
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