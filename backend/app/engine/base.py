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
class EngineJobRequest:
    """引擎无关的生成请求：由 WorkflowModule 从 WorkflowInput 转换而来。"""

    job_type: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineJobStatus:
    """引擎侧任务状态（含进度能力：引擎不支持时 progress 为 None）。"""

    state: str  # queued | running | succeeded | failed | canceled | unknown
    progress: float | None = None  # 0.0 ~ 1.0
    message: str = ""


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
    async def cancel_job(self, engine_job_id: str) -> bool:
        """取消引擎侧任务，返回是否成功。"""
