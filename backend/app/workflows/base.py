"""WorkflowModule 接口规范与标准契约（Phase 0.1 收口；0.1.1 统一异步契约）。

流水线（最终架构）::

    Pipeline → WorkflowModule → EngineAdapter → 具体引擎

**异步原则（固定）**：所有实际执行链路均为 async——Pipeline await WorkflowModule、
WorkflowModule await EngineAdapter、EngineAdapter await 具体引擎；
``validate_input()`` / ``capabilities()`` 等纯数据校验/声明接口保持同步。

- WorkflowModule 只做"能力定义"：模块身份、版本、能力声明、参数定义、
  输入校验、标准输入输出契约；
- 真正的引擎调用**只发生在 EngineAdapter 的实现里**；WorkflowModule 的
  ``execute()`` 通过注入的 EngineAdapter 接口编排任务，不得内嵌任何具体
  引擎（如 ComfyUI）的地址、节点或 Workflow JSON 逻辑；
- 模块之间的契约一律使用本模块的标准类型
  （WorkflowInput / WorkflowOutput / WorkflowValidation / ModuleCapabilities），
  禁止把无约束的 ``dict[str, Any]`` 当作模块间唯一契约。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.engine.base import EngineAdapter, EngineBindingRef


@dataclass(frozen=True)
class ParameterSpec:
    """模块参数定义（能力声明的一部分；Phase 6 Task8 元数据驱动）。

    ``configurable=True`` 的参数才是"可由用户/配方调整的模块 config"（如 img2img.denoise），
    前端按 name/type/min/max/step/enum_values 元数据渲染控件；
    其余参数（input_image / positive_prompt / seed / width…）由通用工作台字段提供。
    """

    name: str
    type: str = "string"  # string | int | float | bool | enum
    required: bool = False
    default: Any = None
    enum_values: tuple[str, ...] = ()
    description: str = ""
    # Task8：用户可读标题（中文 UI 标签；空则前端回落 name）
    title: str = ""
    # Task8：数值范围与步进（float/int 控件渲染依据；None = 不限）
    min: float | None = None
    max: float | None = None
    step: float | None = None
    # Task8：是否允许写入 WorkflowModuleRef.config（唯一由 config 承载的参数集合）
    configurable: bool = False


@dataclass(frozen=True)
class InputSlotSpec:
    """模块输入槽声明（Phase 7 Task5：通用图片输入 Slot 契约，第一版不做复杂 DAG）。

    - role：槽位角色（source | reference | face_reference）；
    - required：本模块执行是否必须提供该槽位的图片；
    - max_count：该槽位允许的最大图片数（默认 1）；
    - description：前端/文档展示说明。

    Job 创建期由 PipelineValidator 校验：未声明角色的输入图 → UNUSED_INPUT_IMAGE；
    必填槽位缺失 → INPUT_IMAGE_REQUIRED；超出 max_count → INPUT_SLOT_LIMIT_EXCEEDED。
    旧模块（未声明 input_slots）仍按 input_required 的兼容语义校验。
    """

    role: str
    required: bool = False
    max_count: int = 1
    description: str = ""


@dataclass(frozen=True)
class ModuleCapabilities:
    """模块能力声明：身份 + 版本 + 参数定义 + 输入/输出语义（Phase 4 Task2）。

    输入/输出语义是 ImageService / Worker 判定 kind / parent / seed 的**唯一依据**，
    禁止再用"有 input_image 就认为是 upscaled"之类的推断。

    - uses_seed：本模块是否真正使用随机 Seed（false 的 Stage 绝不分配/展示 Seed）；
    - input_kind：none | image（模块是否需要输入图片）；
    - input_required：本模块执行是否必须提供输入图片（Phase 5 §十四：模式判定与校验）；
    - input_role：输入图片在模块语义中的角色（第一版固定 source）；
    - output_kind：产出物的 Image kind（original | upscaled | processed）；
    - parent_policy：none | input_image（产出物是否挂到输入图片下）；
    - output_cardinality：单次执行的输出个数（第一版固定 1）；
    - size_mode（Phase 6 Task9）：explicit | input——输出尺寸由工作台显式宽高决定，
      还是跟随输入图片（禁止 UI/详情展示与产物不符的"假宽高"）。
    - allowed_job_kinds（Phase 7 Task2）：本模块允许参与的 Job 类型
      （generate / process）；PipelineValidator 据此校验，不再硬编码"process 必须 upscale"，
      未来 Face Repair / 背景移除等处理模块只需声明能力，无需修改 Validator。
    - can_start_from_image（Phase 7 Task2）：本模块能否作为"以已有图片为起点"的 Pipeline 首模块
      （处理型 Job 的 Stage0 语义：每个 JobItem 对应一张已有图片）。
    - is_generative（Phase 7 Task8）：本模块产出是否构成"生成上下文"
      （Image → Workbench 恢复的锚点，按模块语义判定，不再依赖 seed 数据是否非空）。
    """

    module_id: str
    module_version: str
    title: str = ""
    description: str = ""
    parameters: tuple[ParameterSpec, ...] = ()
    uses_seed: bool = True
    input_kind: str = "none"
    input_required: bool = False
    input_role: str = "source"
    output_kind: str = "original"
    parent_policy: str = "none"
    output_cardinality: int = 1
    size_mode: str = "explicit"
    # Phase 7 Task2：能力驱动的 Job 类型许可（默认仅生成型；处理模块显式声明 process）
    allowed_job_kinds: tuple[str, ...] = ("generate",)
    can_start_from_image: bool = False
    # Phase 7 Task8：生成语义（默认 False：只有明确的生成型模块才可作为生成上下文锚点）
    is_generative: bool = False
    # Phase 7 Task5：通用输入槽声明（source / reference / face_reference）；
    # 空 = 不消费任何输入图（旧模块的 input_required 兼容语义仍生效）
    input_slots: tuple[InputSlotSpec, ...] = ()


@dataclass(frozen=True)
class WorkflowInput:
    """标准输入契约：由 Pipeline 构造，经 validate_input 校验后交给 execute。"""

    values: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowOutput:
    """标准输出契约。

    artifacts：产出物引用（名称 -> DataRoot 相对路径或 URI）；
    metadata：执行元数据（耗时、引擎任务 ID 等）。
    """

    artifacts: Mapping[str, str] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowValidation:
    """输入校验结果。"""

    ok: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class InputImageRef:
    """处理型 StageItem 的输入图片（如高清放大的待处理原图，§二十一）。"""

    image_id: str
    file_name: str
    data: bytes
    width: int = 0
    height: int = 0


@dataclass(frozen=True)
class JobRequestContext:
    """模块构建引擎请求所需的通用 Job 上下文。

    由 PipelineExecutor 从 Job 的通用快照字段构造（不含任何模块专属参数名），
    由具体 WorkflowModule 解释并映射为自己的标准输入 / EngineJobRequest。
    binding：本次请求要使用的 provider binding 身份（§0.2，来自 Job/Stage 固化身份）。
    input_image：处理型模块的输入图片（生成型模块为 None）。
    seed：仅当模块 capabilities().uses_seed == true 时由 Worker 分配；否则为 None
    （Phase 4 Task3：不使用随机性的 Stage 绝不携带"假 Seed"）。
    """

    positive_prompt: str = ""
    negative_prompt: str = ""
    generation_settings: Mapping[str, Any] = field(default_factory=dict)
    seed: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    binding: EngineBindingRef | None = None
    input_image: InputImageRef | None = None
    # Task3（Phase 5.1）：本 Stage 的模块 config（来自 JobStage.config_json，唯一事实源）。
    # 模块参数（如 img2img.denoise）只从这里读取；执行时不再依赖第二事实源。
    module_config: Mapping[str, Any] = field(default_factory=dict)


class WorkflowModule(ABC):
    """生成工作流模块接口（能力定义层）。"""

    module_id: str = "base"
    module_version: str = "0.0.0"

    @abstractmethod
    def capabilities(self) -> ModuleCapabilities:
        """声明模块身份、版本与参数定义。"""

    @abstractmethod
    def validate_input(self, payload: WorkflowInput) -> WorkflowValidation:
        """校验输入；不合法时返回 ok=False 与错误列表。"""

    def validate_config(self, config: Mapping[str, Any]) -> WorkflowValidation:
        """校验模块 config（Phase 5.1 Task5）：Job 创建前由 PipelineValidator 调用。

        config 是模块参数的唯一事实源（Workflow → Recipe → Job → JobStage.config_json 单链）；
        默认无约束；带参数的模块（如 img2img.denoise）覆写本方法。
        """
        return WorkflowValidation(ok=True)

    async def prepare_inputs(self, context: JobRequestContext, engine: EngineAdapter) -> Mapping[str, Any]:
        """可选钩子：执行前准备引擎侧输入（如上传待处理图片，§十三）。

        返回的 dict 会作为 prepared 传给 build_engine_request；默认不做任何事。
        """
        return {}

    def build_engine_request(self, context: JobRequestContext, prepared: Mapping[str, Any] | None = None) -> Any:
        """把 Job 上下文映射为 EngineJobRequest（参数名属于模块契约，不属于 Worker）。

        由具体模块实现；返回类型为 ``app.engine.base.EngineJobRequest``。
        """
        raise NotImplementedError(f"{type(self).__name__} 未实现 build_engine_request")

    @abstractmethod
    async def execute(self, payload: WorkflowInput, engine: EngineAdapter,
                      *, binding: EngineBindingRef | None = None) -> WorkflowOutput:
        """执行工作流（Phase 1+ 由具体模块实现）。

        **必须为 async**（执行链路统一异步：Pipeline → WorkflowModule →
        EngineAdapter → 具体引擎）。只允许通过 ``engine``（EngineAdapter 接口）
        await 引擎调用，不得在模块内实现任何具体引擎的执行逻辑。
        ``binding``：本次请求使用的 provider binding 身份（§0.2，来自固化快照/Stage）。
        """
