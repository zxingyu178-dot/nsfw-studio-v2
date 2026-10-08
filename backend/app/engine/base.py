"""EngineAdapter 接口规范（Phase 0.1 收口）。

流水线（Pipeline → WorkflowModule → EngineAdapter → 具体引擎）中，
**唯一允许调用具体引擎的位置**。未来 ``ComfyUIAdapter`` 等实现放在
``engine/adapters/``，通过 configs 选择，新增适配器不修改核心代码。
本阶段仍然不创建任何具体适配器。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class EngineStatus:
    """引擎健康状态。"""

    online: bool
    detail: str = ""
    engine_name: str = ""
    engine_version: str = ""


@dataclass(frozen=True)
class EngineBindingRef:
    """引擎任务要使用的 provider binding 身份（Phase 3 §0.2）。

    绑定属于**每次请求**，不属于 Adapter 实例——同一个 Adapter 可以交替执行
    basic_generate/v1、upscale/v1、basic_generate/v1 而不需要多套 Adapter。
    """

    module_id: str
    module_version: str = "v1"
    provider: str = "unbound"
    binding_version: str = "v1"
    workflow_hash: str | None = None


@dataclass(frozen=True)
class EngineJobRequest:
    """引擎无关的生成请求：由 WorkflowModule 从 WorkflowInput 转换而来。"""

    binding: EngineBindingRef
    parameters: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def job_type(self) -> str:
        """兼容性别名：等同 binding.module_id（旧代码/测试仍可用）。"""
        return self.binding.module_id


@dataclass(frozen=True)
class EngineJobStatus:
    """引擎侧任务状态（含进度能力：引擎不支持时 progress 为 None）。"""

    state: str  # queued | running | succeeded | failed | canceled | unknown
    progress: float | None = None  # 0.0 ~ 1.0
    message: str = ""
    stage: str = ""
    error_type: str = ""  # 失败时的分类（规范 §三十五）；空则由 Worker 按消息归类


@dataclass(frozen=True)
class EngineOutputFile:
    """引擎产出的单个输出文件（数据在内存中，由 Worker 负责导入 DataRoot）。"""

    filename: str
    data: bytes


class EngineError(Exception):
    """引擎侧错误（带分类，Phase 2 规范 §三十五）。"""

    def __init__(self, error_type: str, message: str, *, transient: bool = False) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.transient = transient  # 仅瞬态网络错误允许自动重试（规范 §三十六）


class EngineAdapter(ABC):
    """生成引擎适配器接口。上层（workers / services）只依赖本接口。"""

    name: str = "base"
    version: str = "0.0.0"

    @abstractmethod
    async def health(self) -> EngineStatus:
        """探测引擎是否可用。"""

    @abstractmethod
    async def submit_job(self, request: EngineJobRequest) -> str:
        """提交生成任务，返回 engine_job_id。"""

    @abstractmethod
    async def get_job_status(self, engine_job_id: str) -> EngineJobStatus:
        """查询引擎侧任务状态与进度。"""

    @abstractmethod
    async def get_job_outputs(self, engine_job_id: str) -> list[EngineOutputFile]:
        """任务成功后取回输出文件（规范 §三十三：导入 DataRoot，不直接引用引擎目录）。"""

    @abstractmethod
    async def cancel_job(self, engine_job_id: str) -> bool:
        """取消引擎侧任务（仅在安全支持时实现；返回是否已请求）。"""
