"""ReferenceGenerateModule — 第三套正式 WorkflowModule（Phase 7 Task6）。

**命名依据（Task6）**：这不是 IPAdapter / FaceID，也不是 Img2Img（不经 VAEEncode +
denoise 的"改图"语义），而是 **Qwen-Image 2.1 原生参考图条件生成**——
`TextEncodeQwenImage21` 把参考图经视觉塔进文本编码器、VAE 编码为 `reference_latents`
拼接进 conditioning，并输出与参考图尺寸匹配的空 latent。因此命名 ``reference_generate``。

- 输入槽：``reference``（必填，v1 只允许 1 张；数据直接复用 Studio 图库，
  包括 Face Asset 已绑定的参考图——不另造图库）；
- 输出：``kind=original``，挂到参考图下（parent_policy=input_image，完整记录 provenance）；
- 当前机器的真实能力与 Gate 实测见 ``docs/REFERENCE_CAPABILITY_INVENTORY.md``；
- 身份固化 / 指纹校验沿用 WorkflowModule → EngineAdapter → provider binding 架构，
  QueueWorker 核心不做任何修改。
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

SEED_MAX = 2147483647
# 参考分辨率语义与 TextEncodeQwenImage21.resolution 一致：参考图重采样到 resolution² 量级，
# 输出 latent 以第一张参考图（重采样后）尺寸为准。
RESOLUTION_MIN = 512
RESOLUTION_MAX = 2048
RESOLUTION_DEFAULT = 1024


def _default_binding(module: "ReferenceGenerateModule") -> EngineBindingRef:
    return EngineBindingRef(
        module_id=module.module_id,
        module_version=module.module_version,
        provider="unbound",
        binding_version="v1",
    )


def _coerce_resolution(raw: Any) -> int | None:
    if raw is None:
        return RESOLUTION_DEFAULT
    if isinstance(raw, bool):  # JSON true/false 不是合法分辨率
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if isinstance(raw, float) and raw != value:
        return None  # 非整数浮点（如 512.5）不接受
    return value


class ReferenceGenerateModule(WorkflowModule):
    """参考图生成模块：已有参考图 + Prompt → 参考条件生成（主体/人物一致性）。"""

    module_id = "reference_generate"
    module_version = "v1"

    def __init__(self, poll_interval_seconds: float = 0.2) -> None:
        self._poll_interval = poll_interval_seconds

    # ===== 能力声明 =====
    def capabilities(self) -> ModuleCapabilities:
        return ModuleCapabilities(
            module_id=self.module_id,
            module_version=self.module_version,
            title="参考图生成",
            description="已有参考图 + Prompt → 参考条件生成（Qwen 原生 reference latents，人物/主体一致性）",
            parameters=(
                ParameterSpec("input_image", "image", required=True,
                              description="参考图（来自 Studio 图库，含 Face Asset 参考图）"),
                ParameterSpec(
                    "resolution", "int", default=RESOLUTION_DEFAULT,
                    min=RESOLUTION_MIN, max=RESOLUTION_MAX, step=64, configurable=True,
                    title="参考分辨率",
                    description=(
                        f"参考图重采样基准（{RESOLUTION_MIN}~{RESOLUTION_MAX}）；"
                        "输出尺寸跟随重采样后的参考图（size_mode=input）"
                    ),
                ),
                ParameterSpec("positive_prompt", "string", required=True),
                ParameterSpec("negative_prompt", "string", default=""),
                ParameterSpec("seed", "int", required=True, description=f"0~{SEED_MAX}（每张独立）"),
            ),
            uses_seed=True,
            input_kind="image",
            input_required=True,
            input_role="reference",
            output_kind="original",
            parent_policy="input_image",
            output_cardinality=1,
            # 输出尺寸跟随（重采样后的）参考图，不是工作台显式宽高
            size_mode="input",
            # Phase 7 Task2/Task8：生成型模块——不允许处理型 Job；产出构成生成上下文锚点
            allowed_job_kinds=("generate",),
            can_start_from_image=True,
            is_generative=True,
            # Phase 7 Task5：v1 只声明 1 张 reference（多参考图受当前 Worker 单输入链限制，后续版本再扩）
            input_slots=(
                InputSlotSpec("reference", required=True, max_count=1,
                              description="参考图（人物/主体）；可直接使用 Face Asset 的参考图"),
            ),
        )

    # ===== config（模块参数唯一事实源） =====
    def validate_config(self, config: Mapping[str, Any]) -> WorkflowValidation:
        errors: list[str] = []
        unknown = set(config.keys()) - {"resolution"}
        if unknown:
            errors.append(f"未知配置项: {', '.join(sorted(unknown))}")
        resolution = _coerce_resolution(config.get("resolution"))
        if resolution is None:
            errors.append("resolution 必须为整数")
        elif not RESOLUTION_MIN <= resolution <= RESOLUTION_MAX:
            errors.append(f"resolution 取值范围为 {RESOLUTION_MIN}~{RESOLUTION_MAX}")
        return WorkflowValidation(ok=not errors, errors=tuple(errors))

    # ===== 标准输入 =====
    def build_input(self, context: JobRequestContext) -> WorkflowInput:
        image = context.input_image
        if not isinstance(image, InputImageRef):
            raise EngineError("WORKFLOW_ERROR", "reference_generate 需要参考图（input_image）")
        if context.seed is None:
            raise EngineError("WORKFLOW_ERROR", "reference_generate 需要 Seed（uses_seed=true）")
        resolution = _coerce_resolution(context.module_config.get("resolution"))
        if resolution is None:
            raise EngineError("WORKFLOW_ERROR", "reference_generate resolution 必须为整数")
        if not RESOLUTION_MIN <= resolution <= RESOLUTION_MAX:
            raise EngineError(
                "WORKFLOW_ERROR",
                f"reference_generate resolution 取值范围为 {RESOLUTION_MIN}~{RESOLUTION_MAX}",
            )
        return WorkflowInput(values={
            "input_image": image,
            "positive_prompt": context.positive_prompt,
            "negative_prompt": context.negative_prompt,
            "seed": int(context.seed),
            "resolution": resolution,
        })

    def validate_input(self, payload: WorkflowInput) -> WorkflowValidation:
        errors: list[str] = []
        if not isinstance(payload.values.get("input_image"), InputImageRef):
            errors.append("input_image 必须为 InputImageRef（已有参考图）")
        try:
            seed = int(payload.values.get("seed", -1))
        except (TypeError, ValueError):
            errors.append("seed 必须为整数")
        else:
            if not 0 <= seed <= SEED_MAX:
                errors.append(f"seed 取值范围为 0~{SEED_MAX}")
        try:
            resolution = int(payload.values.get("resolution", RESOLUTION_DEFAULT))
        except (TypeError, ValueError):
            errors.append("resolution 必须为整数")
        else:
            if not RESOLUTION_MIN <= resolution <= RESOLUTION_MAX:
                errors.append(f"resolution 取值范围为 {RESOLUTION_MIN}~{RESOLUTION_MAX}")
        return WorkflowValidation(ok=not errors, errors=tuple(errors))

    # ===== 引擎侧输入准备（§十三：上传到引擎，仅使用 Studio 唯一命名） =====
    async def prepare_inputs(self, context: JobRequestContext,
                             engine: EngineAdapter) -> Mapping[str, Any]:
        image = context.input_image
        if image is None:
            raise EngineError("WORKFLOW_ERROR", "reference_generate 需要参考图（input_image）")
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
            raise EngineError(
                "WORKFLOW_ERROR", "reference_generate 参考图未准备（prepared.input_image_name）"
            )
        parameters = {
            "input_image": engine_name,
            "positive_prompt": payload.values["positive_prompt"],
            "negative_prompt": payload.values["negative_prompt"],
            "seed": payload.values["seed"],
            "resolution": payload.values["resolution"],
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

        context = JobRequestContext(
            input_image=payload.values.get("input_image"),
            positive_prompt=str(payload.values.get("positive_prompt") or ""),
            negative_prompt=str(payload.values.get("negative_prompt") or ""),
            seed=int(payload.values["seed"]),
            module_config={"resolution": payload.values.get("resolution")},
            binding=binding or _default_binding(self),
        )
        prepared = await self.prepare_inputs(context, engine)
        engine_job_id = await engine.submit_job(self.build_engine_request(context, prepared))
        while True:
            status = await engine.get_job_status(engine_job_id)
            if status.state == "succeeded":
                files = await engine.get_job_outputs(engine_job_id)
                if not files:
                    raise EngineError("OUTPUT_MISSING", "引擎报告成功但没有输出文件")
                return WorkflowOutput(artifacts={"image": files[0].filename},
                                      metadata={"engine_job_id": engine_job_id})
            if status.state in ("failed", "canceled"):
                raise EngineError(status.error_type or "UNKNOWN_ENGINE_ERROR",
                                  status.message or f"引擎任务未成功: {status.state}")
            if status.state == "unknown":
                raise EngineError("UNKNOWN_ENGINE_ERROR", "engine lost track of job")
            await asyncio.sleep(self._poll_interval)