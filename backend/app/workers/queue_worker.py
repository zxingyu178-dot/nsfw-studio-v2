"""单队列 Worker（Phase 2A，规范 §十四-§二十一、§三十六-§三十八）。

原则：
- 系统只有一个逻辑队列、一个 Worker，串行执行（禁止并行）；
- 只消费**已持久化**的 Job（Job 创建只发生在 JobService）；
- 暂停语义：pause_requested → 当前 Item 完成 → 不领取下一个 → Job PAUSED（不强杀）；
- 取消语义：请求 Adapter 安全取消；已完成图片保留；Job 终态 CANCELLED；
- 每张图独立随机 Seed，执行时才分配；已成功 Item 的 Seed 永远保留；
- 瞬态网络错误自动重试 ≤2；系统性失败（离线/OOM/工作流/模型/节点缺失）→
  当前 Job FAILED + 队列自动暂停，等待用户处理（§二十一）；
- 启动时执行崩溃恢复：遗留 RUNNING → INTERRUPTED（§三十七）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import random

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.timeutil import utc_now_iso
from app.engine.base import EngineAdapter, EngineError, EngineJobRequest
from app.engine.errors import classify_engine_message, is_systemic
from app.models import Job, JobItem
from app.services import job_service

logger = logging.getLogger(__name__)

MAX_SUBMIT_RETRIES = 2  # 仅瞬态网络错误（规范 §三十六）
SYSTEM_RANDOM = random.SystemRandom()


class QueuePaused(RuntimeError):
    """系统性失败后队列自动暂停（内存态，用户恢复后清除）。"""


class SingleQueueWorker:
    """单队列串行 Worker（实现 Phase 0 的 QueueWorker 接口语义）。"""

    name = "single-queue-worker"

    def __init__(
        self,
        session_factory: sessionmaker,
        adapter: EngineAdapter,
        *,
        output_importer=None,
        poll_interval_ms: int = 300,
        engine_poll_ms: int = 200,
        seed_upper: int = 2**31 - 1,
    ) -> None:
        self._session_factory = session_factory
        self._adapter = adapter
        self._output_importer = output_importer  # (job, item, outputs) -> list[image_id]，Phase 2C 注入
        self._poll_interval = poll_interval_ms / 1000
        self._engine_poll = engine_poll_ms / 1000
        self._seed_upper = seed_upper
        self._task: asyncio.Task | None = None
        self._running = False
        self._queue_paused = False
        self._queue_paused_reason: str | None = None
        self._current_job_id: str | None = None

    # ===== 生命周期 =====
    def start(self) -> None:
        if self._task is None or self._task.done():
            self._running = True
            self._task = asyncio.create_task(self._run_loop(), name=self.name)

    async def stop(self, timeout: float = 10.0) -> None:
        self._running = False
        if self._task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None

    async def _run_loop(self) -> None:
        logger.info("单队列 Worker 启动 adapter=%s", self._adapter.name)
        while self._running:
            try:
                if self._queue_paused:
                    await asyncio.sleep(self._poll_interval)
                    continue
                job_id = self._pick_next_job()
                if job_id is None:
                    await asyncio.sleep(self._poll_interval)
                    continue
                await self.process_job(job_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Worker 循环异常（继续运行）")
                await asyncio.sleep(max(self._poll_interval, 1.0))

    # ===== 状态 =====
    def status(self) -> dict:
        return {
            "running": self._running,
            "queue_paused": self._queue_paused,
            "queue_paused_reason": self._queue_paused_reason,
            "current_job_id": self._current_job_id,
            "adapter": self._adapter.name,
        }

    def resume_queue(self) -> None:
        """用户处理系统性失败后恢复队列。"""
        self._queue_paused = False
        self._queue_paused_reason = None

    def _pick_next_job(self) -> str | None:
        with self._session_factory() as session:
            job = session.execute(
                select(Job).where(Job.status == "QUEUED")
                .order_by(Job.priority.desc(), Job.queue_position, Job.created_at)
            ).scalars().first()
            if job is None:
                return None
            if job.pause_requested:
                job.status = "PAUSED"
                job_service.record_event(session, job.id, "JOB_PAUSED")
                session.commit()
                return None
            return job.id

    # ===== 单 Job 处理 =====
    async def process_job(self, job_id: str) -> None:
        with self._session_factory() as session:
            job = session.get(Job, job_id)
            if job is None or job.status != "QUEUED":
                return
            job.status = "RUNNING"
            job.started_at = job.started_at or utc_now_iso()
            job_service.record_event(session, job.id, "JOB_STARTED")
            session.commit()
            self._current_job_id = job.id

        outcome = "COMPLETED"
        try:
            items = self._load_items(job_id)
            for item_id in items:
                # 边界检查（规范 §十七/§十九）；已完成 Item 绝不重跑（规范 §十八）
                with self._session_factory() as session:
                    job = session.get(Job, job_id)
                    item = session.get(JobItem, item_id)
                    if job is None or item is None:
                        return
                    if item.status != "QUEUED":
                        continue  # 已完成/已取消/已失败的 Item 不再执行
                    if job.cancel_requested:
                        self._cancel_remaining(session, job)
                        outcome = "CANCELLED"
                        return
                    if job.pause_requested:
                        job.status = "PAUSED"
                        job_service.record_event(session, job.id, "JOB_PAUSED")
                        session.commit()
                        outcome = "PAUSED"
                        return

                result = await self._run_item(job_id, item_id)
                if result == "SYSTEMIC":
                    outcome = "FAILED"
                    return
                if result == "CANCELLED":
                    with self._session_factory() as session:
                        job = session.get(Job, job_id)
                        self._cancel_remaining(session, job)
                    outcome = "CANCELLED"
                    return
                if result == "PAUSED":
                    outcome = "PAUSED"
                    return
        finally:
            self._finish_job(job_id, outcome)
            self._current_job_id = None

    def _load_items(self, job_id: str) -> list[str]:
        with self._session_factory() as session:
            return list(session.execute(
                select(JobItem.id).where(JobItem.job_id == job_id).order_by(JobItem.item_index)
            ).scalars())

    def _cancel_remaining(self, session: Session, job: Job) -> None:
        job.status = "CANCELLED"
        job.finished_at = utc_now_iso()
        for item in session.execute(select(JobItem).where(
            JobItem.job_id == job.id, JobItem.status.in_(("QUEUED", "RUNNING", "INTERRUPTED"))
        )).scalars():
            item.status = "CANCELLED"
            item.finished_at = utc_now_iso()
        job_service.record_event(session, job.id, "JOB_CANCELLED")
        session.commit()

    def _finish_job(self, job_id: str, outcome: str) -> None:
        with self._session_factory() as session:
            job = session.get(Job, job_id)
            if job is None or job.status in ("CANCELLED", "PAUSED", "INTERRUPTED"):
                return
            completed = sum(1 for item in job.items if item.status == "COMPLETED")
            failed = sum(1 for item in job.items if item.status == "FAILED")
            job.completed_count = completed
            if outcome == "CANCELLED":
                job.status = "CANCELLED"
            elif outcome == "PAUSED":
                job.status = "PAUSED"
            elif failed > 0:
                job.status = "FAILED"  # 部分成功由 Item 统计表达（规范 §六）
            else:
                job.status = "COMPLETED"
            if job.status in ("COMPLETED", "FAILED", "CANCELLED"):
                job.finished_at = utc_now_iso()
            job_service.record_event(session, job.id, f"JOB_{job.status}")
            session.commit()

    # ===== 单 Item 执行 =====
    async def _run_item(self, job_id: str, item_id: str) -> str:
        """返回：COMPLETED / FAILED / CANCELLED / PAUSED / SYSTEMIC。"""
        with self._session_factory() as session:
            item = session.get(JobItem, item_id)
            job = session.get(Job, job_id)
            if item is None or job is None:
                return "FAILED"
            # Seed 规则（规范 §九）：执行时才分配随机 Seed；固定 Seed 模式用 base+index
            snapshot = json.loads(job.workbench_snapshot_json)
            if snapshot.get("seed_mode") == "fixed" and snapshot.get("seed") is not None:
                seed = int(snapshot["seed"]) + int(item.item_index)
            else:
                seed = SYSTEM_RANDOM.randint(0, self._seed_upper)
            item.status = "RUNNING"
            item.started_at = utc_now_iso()
            item.seed = seed
            item.current_stage = "submit"
            item.progress = 0.0
            job_service.record_event(session, job_id, "ITEM_STARTED", item_id=item.id, payload={"seed": seed})
            session.commit()
            request = EngineJobRequest(
                job_type="basic_generate",
                parameters={
                    "positive_prompt": job.positive_prompt_snapshot,
                    "negative_prompt": job.negative_prompt_snapshot,
                    "width": json.loads(job.generation_settings_json).get("width", 1024),
                    "height": json.loads(job.generation_settings_json).get("height", 1024),
                    "seed": seed,
                },
                metadata={"job_id": job.id, "item_id": item.id},
            )

        # 提交（瞬态网络错误重试 ≤2，规范 §三十六）
        engine_job_id: str | None = None
        attempt = 0
        while True:
            try:
                engine_job_id = await self._adapter.submit_job(request)
                break
            except EngineError as error:
                if error.error_type == "ENGINE_OFFLINE":
                    return self._systemic_failure(job_id, item_id, error)
                attempt += 1
                if error.transient and attempt <= MAX_SUBMIT_RETRIES:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                return self._item_failed(job_id, item_id, error.error_type, error.message)
            except Exception as error:  # 未知异常按未知引擎错误处理
                return self._item_failed(job_id, item_id, "UNKNOWN_ENGINE_ERROR", str(error))

        with self._session_factory() as session:
            item = session.get(JobItem, item_id)
            item.engine_job_id = engine_job_id
            session.commit()

        # 轮询进度
        cancel_sent = False
        while True:
            await asyncio.sleep(self._engine_poll)
            with self._session_factory() as session:
                job = session.get(Job, job_id)
                if job is not None and job.cancel_requested and not cancel_sent:
                    await self._adapter.cancel_job(engine_job_id)
                    cancel_sent = True
            try:
                status = await self._adapter.get_job_status(engine_job_id)
            except EngineError as error:
                if error.error_type == "ENGINE_OFFLINE":
                    return self._systemic_failure(job_id, item_id, error)
                item_failed_type = "ENGINE_NETWORK"
                with self._session_factory() as session:
                    item = session.get(JobItem, item_id)
                    item.retry_count += 1
                    retry = error.transient and item.retry_count <= MAX_SUBMIT_RETRIES
                    session.commit()
                if retry:
                    continue
                return self._item_failed(job_id, item_id, item_failed_type, error.message)
            except Exception as error:
                return self._item_failed(job_id, item_id, "UNKNOWN_ENGINE_ERROR", str(error))

            self._update_progress(item_id, status)

            if status.state == "succeeded":
                outputs = []
                try:
                    outputs = await self._adapter.get_job_outputs(engine_job_id)
                except Exception as error:
                    logger.warning("取回引擎输出失败: %s", error)
                image_ids = self._import_outputs(job_id, item_id, outputs)
                with self._session_factory() as session:
                    item = session.get(JobItem, item_id)
                    job = session.get(Job, job_id)
                    item.status = "COMPLETED"
                    item.progress = 1.0
                    item.current_stage = "done"
                    item.finished_at = utc_now_iso()
                    if image_ids:
                        item.image_id = image_ids[0]
                    if job is not None:
                        job.completed_count = sum(1 for it in job.items if it.status == "COMPLETED")
                    job_service.record_event(session, job_id, "ITEM_COMPLETED", item_id=item.id,
                                             payload={"image_ids": image_ids})
                    session.commit()
                return "COMPLETED"
            if status.state == "canceled":
                with self._session_factory() as session:
                    item = session.get(JobItem, item_id)
                    item.status = "CANCELLED"
                    item.finished_at = utc_now_iso()
                    job_service.record_event(session, job_id, "ITEM_CANCELLED", item_id=item.id)
                    session.commit()
                return "CANCELLED"
            if status.state == "failed":
                error_type = classify_engine_message(status.message)
                if is_systemic(error_type):
                    return self._systemic_failure(job_id, item_id,
                                                  EngineError(error_type, status.message or error_type))
                return self._item_failed(job_id, item_id, error_type, status.message or error_type)
            if status.state == "unknown":
                # 引擎不认识该任务（如重启后丢失）：按可恢复失败处理，不自动重试
                return self._item_failed(job_id, item_id, "UNKNOWN_ENGINE_ERROR", "engine lost track of job")

    def _update_progress(self, item_id: str, status) -> None:
        with self._session_factory() as session:
            item = session.get(JobItem, item_id)
            if item is None:
                return
            item.current_stage = status.stage or item.current_stage
            if status.progress is not None:
                item.progress = float(status.progress)
            session.commit()
            job_service.record_event(
                session, item.job_id, "ITEM_PROGRESS", item_id=item_id,
                payload={"progress": item.progress, "stage": item.current_stage},
            )
            session.commit()

    def _import_outputs(self, job_id: str, item_id: str, outputs) -> list[str]:
        if not outputs or self._output_importer is None:
            return []
        try:
            with self._session_factory() as session:
                job = session.get(Job, job_id)
                item = session.get(JobItem, item_id)
                return list(self._output_importer(job, item, outputs) or [])
        except Exception:
            logger.exception("导入引擎输出失败（Item 标记 STORAGE_ERROR）")
            self._item_failed(job_id, item_id, "STORAGE_ERROR", "导入引擎输出失败")
            return []

    def _item_failed(self, job_id: str, item_id: str, error_type: str, message: str) -> str:
        with self._session_factory() as session:
            item = session.get(JobItem, item_id)
            item.status = "FAILED"
            item.error_type = error_type
            item.error_message = message
            item.finished_at = utc_now_iso()
            job_service.record_event(session, job_id, "ITEM_FAILED", item_id=item_id,
                                     payload={"error_type": error_type, "message": message})
            session.commit()
        return "FAILED"

    def _systemic_failure(self, job_id: str, item_id: str, error: EngineError) -> str:
        """系统性失败（规范 §二十一）：Job FAILED + 队列自动暂停。"""
        with self._session_factory() as session:
            item = session.get(JobItem, item_id)
            if item is not None:
                item.status = "FAILED"
                item.error_type = error.error_type
                item.error_message = error.message
                item.finished_at = utc_now_iso()
            job = session.get(Job, job_id)
            if job is not None:
                job.status = "FAILED"
                job.error_type = error.error_type
                job.error_message = error.message
                job.finished_at = utc_now_iso()
                for queued_item in session.execute(select(JobItem).where(
                    JobItem.job_id == job.id, JobItem.status == "QUEUED"
                )).scalars():
                    queued_item.status = "CANCELLED"
                    queued_item.finished_at = utc_now_iso()
                job_service.record_event(session, job.id, "JOB_FAILED",
                                         payload={"error_type": error.error_type, "message": error.message})
            session.commit()
        self._queue_paused = True
        self._queue_paused_reason = f"{error.error_type}: {error.message}"
        logger.error("系统性失败，队列已自动暂停: %s", self._queue_paused_reason)
        return "SYSTEMIC"

    # ===== 崩溃恢复（规范 §三十七、§三十八） =====
    async def recover_interrupted(self) -> list[str]:
        """启动时：RUNNING → INTERRUPTED（job_service），并对有 engine_job_id 的 Item
        向引擎核对（§三十八）；确认成功则导入图片落 COMPLETED。"""
        with self._session_factory() as session:
            interrupted_ids = job_service.mark_interrupted_at_startup(session)
        recovered: list[str] = []
        for job_id in interrupted_ids:
            with self._session_factory() as session:
                items = session.execute(select(JobItem).where(
                    JobItem.job_id == job_id, JobItem.status == "INTERRUPTED"
                )).scalars().all()
                targets = [(item.id, item.engine_job_id) for item in items]
            for item_id, engine_job_id in targets:
                if not engine_job_id:
                    continue
                try:
                    status = await self._adapter.get_job_status(engine_job_id)
                except Exception:
                    continue
                if status.state != "succeeded":
                    continue  # 无法确认成功 → 保持可恢复（用户续跑时用新随机 Seed）
                outputs = []
                try:
                    outputs = await self._adapter.get_job_outputs(engine_job_id)
                except Exception:
                    continue
                with self._session_factory() as session:
                    item = session.get(JobItem, item_id)
                    job = session.get(Job, job_id)
                    image_ids = self._import_outputs(job_id, item_id, outputs)
                    item.status = "COMPLETED"
                    item.progress = 1.0
                    item.finished_at = utc_now_iso()
                    if image_ids:
                        item.image_id = image_ids[0]
                    if job is not None:
                        job.completed_count = sum(1 for it in job.items if it.status == "COMPLETED")
                    job_service.record_event(session, job_id, "ITEM_RECOVERED", item_id=item_id,
                                             payload={"image_ids": image_ids})
                    session.commit()
                recovered.append(item_id)
        if recovered:
            logger.info("崩溃恢复：核对完成 %s 个 Item", len(recovered))
        return recovered
