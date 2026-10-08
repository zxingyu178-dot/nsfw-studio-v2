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
    """模块参数定义（能力声明的一部分）。"""

    name: str
    type: str = "string"  # string | int | float | bool | enum
    required: bool = False
    default: Any = None
    enum_values: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class ModuleCapabilities:
    """模块能力声明：身份 + 版本 + 参数定义。"""

    module_id: str
    module_version: str
    title: str = ""
    description: str = ""
    parameters: tuple[ParameterSpec, ...] = ()


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
    """

    positive_prompt: str = ""
    negative_prompt: str = ""
    generation_settings: Mapping[str, Any] = field(default_factory=dict)
    seed: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)
    binding: EngineBindingRef | None = None
    input_image: InputImageRef | None = None


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
