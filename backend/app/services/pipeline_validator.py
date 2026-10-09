"""PipelineValidator（Phase 5.1 Task4/Task5）：Pipeline 合法性唯一验证入口。

在 **Job 创建前**（JobService）依据 ModuleCapabilities 验证，禁止把判断写进 QueueWorker：

- 同一 module_id 不允许重复出现（第一版明确禁止 → PIPELINE_DUPLICATE_MODULE，Task4）；
- 每个模块必须已注册且**版本真实存在**（未知 module_id / 未注册 module_version
  都在创建期拒绝，而不是执行期才炸；Task4/Task5：fail fast，不回退到 id 级）；
- 模块 config 必须通过模块自己的 ``validate_config`` 钩子（config 是模块参数唯一事实源）；
- Stage 0 输入配对（P0：输入图片不能被静默忽略）：
  - ``input_required=false`` 的模块携带输入图 → ``UNUSED_INPUT_IMAGE``；
  - ``input_required=true`` 的模块缺少输入图 → ``INPUT_IMAGE_REQUIRED``；
- Stage N（N>0）必须能接收 Stage N-1 的输出（output_kind → input_kind 链式检查）；
- Job kind 能力驱动（Phase 7 Task2）：模块必须声明允许当前 job_kind（allowed_job_kinds），
  处理型 Job 的首个模块必须 can_start_from_image=true——不再硬编码"process 必须 upscale"，
  未来新增处理模块（Face Repair / 背景移除）只需声明能力，不需要修改本 Validator。

顺序语义（Task4）：Validator 只判断"这条 Pipeline 是否合法"，**绝不重排**——
顺序由用户/Recipe/Workbench 提供，执行层严格保持。
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
        """解析模块实例与能力：module_id / module_version 未注册 → 4xx（创建期拒绝）。

        Phase 6 Task4/Task5：版本级解析**不再回退**到 id 级——
        "未知 / 未注册 module_version" 必须在 Job 创建期就拒绝（fail fast），
        而不是创建一个执行期必然失败的 Job。HISTORY/RECIPE 恢复同样适用：
        被固化的代码版本已不存在时，明确 4xx，绝不静默改跑别的版本。
        """
        module_id = str(module.get("module_id") or "")
        module_version = module.get("module_version")
        try:
            instance = self._registry.get(module_id, str(module_version)) if module_version else self._registry.get(module_id)
        except EngineError as error:
            raise ValidationError(error.message, code=error.error_type) from error
        return instance, instance.capabilities()

    def validate(
        self,
        modules: list[dict[str, Any]],
        *,
        job_kind: str,
        has_input_image: bool,
        input_roles: dict[str, int] | None = None,
    ) -> None:
        """校验整条 Pipeline；不合法时抛 ValidationError（4xx，Job 不被创建）。

        ``input_roles``（Phase 7 Task5）：Stage0 输入图的「角色 → 数量」；
        未提供时回退为 ``{"source": 1} if has_input_image else {}``（旧调用方兼容）。
        """
        if not modules:
            raise ValidationError("Pipeline 至少需要一个 WorkflowModule", code="PIPELINE_INVALID")

        # 0) Task4（Phase 6）：同一 module_id 不允许在 Pipeline 中重复出现（第一版明确禁止；
        #    由本 Validator 承担，而不是在工厂里静默去重）
        seen: set[str] = set()
        for module in modules:
            module_id = str(module.get("module_id") or "")
            if module_id in seen:
                raise ValidationError(
                    f"Pipeline 不允许同一模块重复出现: {module_id}",
                    code="PIPELINE_DUPLICATE_MODULE",
                )
            seen.add(module_id)

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

        # 2) Job kind 能力驱动（Phase 7 Task2）：不再硬编码"process 必须且只能是 upscale"——
        #    - 每个模块必须声明允许当前 job_kind（allowed_job_kinds）；
        #    - 处理型 Job（每个 JobItem = 一张已有图片）的**首个模块**必须
        #      can_start_from_image=true（以已有图片为起点）。
        #    未来 Face Repair / 背景移除等处理模块只需声明能力，不需要修改本 Validator。
        for _instance, capabilities in resolved:
            if job_kind not in capabilities.allowed_job_kinds:
                raise ValidationError(
                    f"模块 {capabilities.module_id} 不允许用于 {job_kind} 型任务"
                    f"（allowed_job_kinds={list(capabilities.allowed_job_kinds)}）",
                    code="PIPELINE_INVALID",
                )
        if job_kind == "process" and not resolved[0][1].can_start_from_image:
            raise ValidationError(
                f"处理型 Job 的首个模块 {resolved[0][1].module_id} 不能以已有图片为起点"
                "（can_start_from_image=false）",
                code="PIPELINE_INVALID",
            )

        capabilities_list = [capabilities for _instance, capabilities in resolved]
        first = capabilities_list[0]

        # 3) Stage 0 输入配对（P0：输入图片不能被静默忽略；Phase 7 Task5：Slot 契约驱动）
        provided = (
            dict(input_roles)
            if input_roles is not None
            else ({"source": 1} if has_input_image else {})
        )
        if first.input_slots:
            # 模块声明了输入 Slot：按角色校验（未声明角色 → 不被消费；必填缺失 → 拒绝；
            # 超量 → 拒绝）——新增 Reference / Face 模块只需声明 slot，不需要修改 Validator。
            declared = {slot.role: slot for slot in first.input_slots}
            for role, count in provided.items():
                if role not in declared:
                    raise ValidationError(
                        f"输入图片未被 Pipeline 使用：首个模块 {first.module_id} 未声明输入槽 {role}",
                        code="UNUSED_INPUT_IMAGE",
                    )
                if count > declared[role].max_count:
                    raise ValidationError(
                        f"输入槽 {role} 超出上限：{first.module_id} 最多 {declared[role].max_count} 张"
                        f"（收到 {count} 张）",
                        code="INPUT_SLOT_LIMIT_EXCEEDED",
                    )
            missing = [
                slot.role for slot in first.input_slots
                if slot.required and provided.get(slot.role, 0) < 1
            ]
            if missing:
                raise ValidationError(
                    f"Pipeline 需要输入图片但未提供：{first.module_id} 必填输入槽 "
                    f"{', '.join(missing)}",
                    code="INPUT_IMAGE_REQUIRED",
                )
        else:
            # 兼容旧声明（未声明 input_slots 的模块）：沿用 input_required 语义
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