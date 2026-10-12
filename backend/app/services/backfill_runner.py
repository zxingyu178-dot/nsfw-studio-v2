"""Thumbnail/Preview 后台回填 runner（Phase 0.11.1 P1-3）。

- 单 worker、低并发（worker 内逐张处理，并发度 1）；不占 GPU（纯 Pillow CPU）；
- 进程内状态（Studio 重启后再次调用可重算缺失，无持久化任务要求）；
- 由 FastAPI lifespan 持有唯一实例，应用关闭时干净停止；
- 与现有 engine_runtime 单例互不干扰（独立线程、独立 session）。
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.models import Image
from app.services import thumbnail_service
from app.storage.manager import StorageManager

logger = logging.getLogger(__name__)


class ThumbnailBackfillRunner:
    """单例回填执行器：同一时间只允许一个回填任务。"""

    def __init__(self, session_factory: sessionmaker, storage: StorageManager) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._guard = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._state: dict[str, Any] = {
            "running": False, "done": 0, "total": 0, "failed": 0,
            "kind": "thumbnail", "limit": None,
        }

    def start(self, *, kind: str = "thumbnail", limit: int | None = None) -> dict[str, Any]:
        """启动回填；若已有任务在跑则直接返回当前状态（不重复起）。"""
        if kind not in ("thumbnail", "preview"):
            from app.core.errors import ValidationError
            raise ValidationError(f"非法回填类型: {kind}", code="BACKFILL_KIND_INVALID")
        with self._guard:
            if self._state["running"]:
                return self._snapshot()
            # 同步计算待处理列表（轻量 SELECT），使 total 立即可知
            with self._session_factory() as session:
                pending = thumbnail_service.iter_images_missing_variant(session, kind)
            self._stop.clear()
            self._state = {
                "running": True, "done": 0, "total": len(pending), "failed": 0,
                "kind": kind, "limit": limit,
            }
            self._thread = threading.Thread(
                target=self._run, args=(pending,), name="thumbnail-backfill", daemon=True,
            )
            self._thread.start()
            return self._snapshot()

    def status(self) -> dict[str, Any]:
        with self._guard:
            return self._snapshot()

    def stop(self) -> dict[str, Any]:
        """请求停止（置 flag，当前张完成后停止），并等待 worker 退出后返回最终状态。"""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=10)
        with self._guard:
            return self._snapshot()

    def shutdown(self) -> None:
        """应用关闭：请求停止并等待干净退出。"""
        self.stop()

    def _snapshot(self) -> dict[str, Any]:
        state = dict(self._state)
        if self._thread is not None and not self._thread.is_alive():
            state["running"] = False
        return state

    def _run(self, pending: list[str]) -> None:
        kind = self._state["kind"]
        limit = self._state["limit"]
        try:
            for image_id in pending:
                if self._stop.is_set():
                    break
                with self._session_factory() as session:
                    image = session.get(Image, image_id)
                    if image is None:
                        continue
                    try:
                        thumbnail_service.get_or_create_variant(session, self._storage, image, kind)
                        with self._guard:
                            self._state["done"] += 1
                    except Exception:  # noqa: BLE001 —— 单张失败跳过不阻断
                        session.rollback()
                        with self._guard:
                            self._state["failed"] += 1
                if limit is not None and self._state["done"] >= limit:
                    break
        except Exception:  # noqa: BLE001 —— worker 主循环异常不得拖垮进程
            logger.exception("thumbnail backfill worker 异常退出")
        finally:
            with self._guard:
                self._state["running"] = False
