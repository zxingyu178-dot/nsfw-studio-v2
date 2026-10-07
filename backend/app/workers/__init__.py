"""Worker 层。Phase 0 仅有接口占位，不启动任何线程 / 进程。"""
from app.workers.base import QueueWorker

__all__ = ["QueueWorker"]
