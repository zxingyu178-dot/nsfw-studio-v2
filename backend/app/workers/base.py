"""Worker 框架占位（Phase 0 规范 §四 workers 模块）。

Phase 0 只定义接口，不启动任何线程 / 进程；
Phase 1 将实现单个 ``QueueWorker``，消费生成任务队列并把工作流
执行委托给 WorkflowModule / EngineAdapter。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class QueueWorker(ABC):
    """队列 Worker 基类。"""

    name: str = "queue-worker"

    @abstractmethod
    def start(self) -> None:
        """启动 Worker（Phase 1 实现）。"""

    @abstractmethod
    def stop(self, timeout: float = 10.0) -> None:
        """优雅停止 Worker（Phase 1 实现）。"""

    @abstractmethod
    def submit(self, job: dict[str, Any]) -> str:
        """提交任务，返回 job_id（Phase 1 实现）。"""

    @abstractmethod
    def status(self) -> dict[str, Any]:
        """返回运行状态快照（Phase 1 实现）。"""
