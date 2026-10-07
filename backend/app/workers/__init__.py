"""Worker 层：消费者接口规范（Job 创建属于 API/JobService，见模块 docstring）。"""
from app.workers.base import QueueWorker, WorkerStatus

__all__ = ["QueueWorker", "WorkerStatus"]
