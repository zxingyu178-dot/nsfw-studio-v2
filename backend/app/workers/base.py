"""Worker 接口规范（Phase 0.1 职责收口）。

职责边界（最终原则）::

    API / JobService → 创建并持久化 Job
    Queue / Worker   → 只消费已经存在的 Job

因此 Worker **不提供** ``submit(job)`` 之类的创建入口——Job 的创建与持久化
属于 API / JobService（Phase 1 实现）；Worker 的消费入口是
``process_job(job_id)``，只处理已存在的 Job。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerStatus:
    """Worker 运行状态快照。"""

    running: bool
    pending_jobs: int | None = None  # 队列不可观测时为 None
    detail: str = ""


class QueueWorker(ABC):
    """队列 Worker 基类（消费者，不是 Job 的创建者）。"""

    name: str = "queue-worker"

    @abstractmethod
    def start(self) -> None:
        """启动 Worker（Phase 1 实现）。"""

    @abstractmethod
    def stop(self, timeout: float = 10.0) -> None:
        """优雅停止 Worker（Phase 1 实现）。"""

    @abstractmethod
    def status(self) -> WorkerStatus:
        """返回运行状态快照（Phase 1 实现）。"""

    @abstractmethod
    def process_job(self, job_id: str) -> None:
        """处理一个**已存在**（已由 JobService 创建并持久化）的 Job。

        具体实现 Phase 1 提供；本接口禁止衍生出 Job 创建/持久化职责。
        """
