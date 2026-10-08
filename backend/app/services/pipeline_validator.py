"""PipelineValidator（Phase 5.1 Task4/Task5）：Pipeline 合法性唯一验证入口。

在 **Job 创建前**（JobService）依据 ModuleCapabilities 验证，禁止把判断写进 QueueWorker：

- 每个模块必须已注册且版本存在（未知模块在创建期拒绝，而不是执行期才炸）；
- 模块 config 必须通过模块自己的 ``validate_config`` 钩子（config 是模块参数唯一事实源）；
- Stage 0 输入配对（P0：输入图片不能被静默忽略）：
  - ``input_required=false`` 的模块携带输入图 → ``UNUSED_INPUT_IMAGE``；
  - ``input_required=true`` 的模块缺少输入图 → ``INPUT_IMAGE_REQUIRED``；
- Stage N（N>0）必须能接收 Stage N-1 的输出（output_kind → input_kind 链式检查）；
- 处理型 Job（process）的 Pipeline 必须且只能是 upscale。
"""
from __future__ import annotations

from typing import Any

from app.core.errors import ValidationError
from app.engine.base import EngineError
from app.workflows.base import ModuleCapabilities, WorkflowModule
from app.workflows.registry import ModuleRegistry, default_registry

# 可作为后续 Stage 输入的输出类型（Studio 全部产出均为图片产物）
IMAGE_OUTPUT_KINDS = ("original", "upscaled", "processed")


class PipelineValidator:
    def __init__(self, registry: ModuleRegistry | None = None) -> None:
        self._registry = registry or default_registry()

    def _resolve(self, module: dict[str, Any]) -> tuple[WorkflowModule, ModuleCapabilities]:
        """解析模块实例与能力：module_id 未注册 → 4xx（创建期拒绝）。

        版本级解析与创建期校验解耦：固化版本暂不存在时（如模拟系统升级 v2），
        结构校验按同 id 模块能力进行；执行侧仍按 Stage 固化版本严格解析
        （发现不一致会在 Worker 阶段明确失败，绝不静默改跑别的版本）。
        """
        module_id = str(module.get("module_id") or "")
        module_version = module.get("module_version")
        if module_version:
            try:
                instance = self._registry.get(module_id, str(module_version))
            except EngineError:
                pass  # 回退到 id 级能力校验
            else:
                return instance, instance.capabilities()
        try:
            instance = self._registry.get(module_id)
        except EngineError as error:
            raise ValidationError(error.message, code=error.error_type) from error
        return instance, instance.capabilities()

    def validate(
        self,
        modules: list[dict[str, Any]],
        *,
        job_kind: str,
        has_input_image: bool,
    ) -> None:
        """校验整条 Pipeline；不合法时抛 ValidationError（4xx，Job 不被创建）。"""
        if not modules:
            raise ValidationError("Pipeline 至少需要一个 WorkflowModule", code="PIPELINE_INVALID")

        resolved = [self._resolve(module) for module in modules]

        # 1) 模块 config 自检（WorkflowModuleRefModel.config 是唯一入口）
        for module, (instance, capabilities) in zip(modules, resolved):
            config = module.get("config")
            if config is not None and not isinstance(config, dict):
                raise ValidationError(
                    f"{capabilities.module_id} config 必须为对象", code="MODULE_CONFIG_INVALID"
                )
            validation = instance.validate_config(config or {})
            if not validation.ok:
                raise ValidationError(
                    f"{capabilities.module_id} 配置非法: {'; '.join(validation.errors)}",
                    code="MODULE_CONFIG_INVALID",
                )

        # 2) 处理型 Job：Phase 3 语义不变（只跑处理模块，每个 JobItem 对应一张已有图片）
        if job_kind == "process":
            if [module.get("module_id") for module in modules] != ["upscale"]:
                raise ValidationError(
                    "处理型 Job 的 Pipeline 必须且只能是 upscale", code="PIPELINE_INVALID"
                )

        capabilities_list = [capabilities for _instance, capabilities in resolved]
        first = capabilities_list[0]

        # 3) Stage 0 输入配对（P0：输入图片不能被静默忽略）
        if has_input_image and not first.input_required:
            raise ValidationError(
                f"输入图片未被 Pipeline 使用：首个模块 {first.module_id} 不消费输入图（input_required=false）",
                code="UNUSED_INPUT_IMAGE",
            )
        if not has_input_image and first.input_required:
            raise ValidationError(
                f"Pipeline 需要输入图片但未提供：{first.module_id}（input_required=true）",
                code="INPUT_IMAGE_REQUIRED",
            )

        # 4) Stage 链式检查：Stage N 必须能接收 Stage N-1 输出
        for index in range(1, len(capabilities_list)):
            previous = capabilities_list[index - 1]
            current = capabilities_list[index]
            if current.input_required and current.input_kind != "image":
                raise ValidationError(
                    f"Stage {index}（{current.module_id}）能力声明矛盾：input_required=true 但 input_kind={current.input_kind}",
                    code="PIPELINE_INVALID",
                )
            if not current.input_required:
                raise ValidationError(
                    f"Stage {index}（{current.module_id}）不消费上一 Stage 输出，链式 Pipeline 非法",
                    code="PIPELINE_INVALID",
                )
            if previous.output_kind not in IMAGE_OUTPUT_KINDS:
                raise ValidationError(
                    f"Stage {index} 无法接收 Stage {index - 1}（{previous.module_id}）的输出："
                    f"output_kind={previous.output_kind} 不是图片产物",
                    code="PIPELINE_INVALID",
                )