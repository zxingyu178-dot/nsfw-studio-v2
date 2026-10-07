"""进程内事件总线：为 SSE 提供实时通知（Phase 2 规范 §二十三）。

原则：SSE 只负责"实时通知"，数据库 Job 状态才是唯一事实源；
客户端重连后必须重新 GET Job 状态，本总线不提供历史回放。
线程安全：publish 可在任意线程调用（FastAPI 同步端点运行于线程池）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading

logger = logging.getLogger(__name__)


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self._lock:
            self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.discard(queue)

    def publish(self, event: dict) -> None:
        """向所有订阅者广播事件（非订阅者时为 no-op）。"""
        subscribers = list(self._subscribers)
        if not subscribers:
            return
        try:
            data = json.dumps(event, ensure_ascii=False)
        except (TypeError, ValueError):
            return
        loop = self._loop

        def _put() -> None:
            for queue in subscribers:
                if not queue.full():
                    queue.put_nowait(data)

        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(_put)
        else:
            _put()

    def subscriber_count(self) -> int:
        return len(self._subscribers)
