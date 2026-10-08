"""单队列 Worker（Phase 3：多阶段流水线执行）。

原则：
- 系统只有一个逻辑队列、一个 Worker，串行执行（禁止并行）；
- 只消费**已持久化**的 Job（Job 创建只发生在 JobService）；
- 执行真源 = JobStage + workflow_snapshot（§二十三），绝不读取当前配置；
- Stage Gate（§六）：Stage N 全部 StageItem COMPLETED → Stage COMPLETED → 才启动 Stage N+1；
  任一 StageItem FAILED → Stage FAILED → Job FAILED → 后续 Stage 不启动；
- 暂停语义（§七）：pause_requested → 当前 StageItem 完成 → 不领取下一个 → Stage/Job PAUSED（不强杀）；
- 取消语义（§七）：请求 Adapter 安全取消；已完成的原图/高清图全部保留；Job 终态 CANCELLED；
- Seed 规则（§0.4）：默认每张独立随机 Seed；仅单张精确复现（seed_mode=fixed 且 count=1）使用固定
  Seed，且固定 Seed 只作用于第一个 Stage；
- 瞬态网络错误自动重试 ≤2；系统性失败（离线/OOM/工作流/模型/节点/绑定缺失）→
  当前 Job FAILED + 队列自动暂停（§二十一）；
- §0.1：Worker/代码级意外异常 → 当前 Job/Stage 标记 INTERRUPTED（保留 engine_job_id 等恢复信息）
  + queue_paused=true + WORKER_INTERNAL_ERROR；正常 shutdown 的 CancelledError 仍按崩溃恢复处理
  （不写终态）；
- §十：StageItem 执行总超时（默认 30 分钟，可由 Stage config_json.execution_timeout 覆盖）
  → ENGINE_TIMEOUT，不自动重试；
- §八/§九：崩溃恢复按 StageItem 核对（engine_job_id + 引擎 history），history 丢失时可用
  Studio 自己的输出命名规则做文件级兜底核对（只处理 Studio 自己命名的输出）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.timeutil import utc_now_iso
from app.engine.base import EngineAdapter, EngineBindingRef, EngineError, EngineJobRequest
from app.engine.errors import classify_engine_message, is_systemic
from app.models import Job, JobItem, JobStage, JobStageItem
from app.services import job_service
from app.workflows.pipeline import PipelineExecutor

logger = logging.getLogger(__name__)

MAX_SUBMIT_RETRIES = 2  # 仅瞬态网络错误（规范 §三十六）
SYSTEM_RANDOM = random.SystemRandom()
DEFAULT_STAGE_TIMEOUT_SECONDS = 1800.0  # §十：本机 6GB 显存冷启动较慢，默认宽松


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
        input_loader=None,
        pipeline: PipelineExecutor | None = None,
        poll_interval_ms: int = 300,
        engine_poll_ms: int = 200,
        seed_upper: int = 2**31 - 1,
        stage_timeout_seconds: float = DEFAULT_STAGE_TIMEOUT_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._adapter = adapter
        # §三：模块解析与引擎请求构造的唯一入口（Worker 不知道任何模块的参数结构）
        self._pipeline = pipeline or PipelineExecutor()
        # (job, stage_item, outputs) -> list[image_id]，由 main.py 注入（Phase 3 按 StageItem 判定）
        self._output_importer = output_importer
        # (image_id) -> InputImageRef，处理型 Stage 的输入图片加载（§十三/§二十一）
        self._input_loader = input_loader
        self._poll_interval = poll_interval_ms / 1000
        self._engine_poll = engine_poll_ms / 1000
        self._seed_upper = seed_upper
        self._stage_timeout = float(stage_timeout_seconds)
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
                # §0.1：Worker 循环级代码异常同样暂停队列，禁止继续领取新 Job
                logger.exception("Worker 循环异常（队列暂停，等待用户处理）")
                self._pause_queue("WORKER_INTERNAL_ERROR: Worker 循环异常")
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

    def _pause_queue(self, reason: str) -> None:
        self._queue_paused = True
        self._queue_paused_reason = reason
        logger.error("队列已自动暂停: %s", reason)

    def _pick_next_job(self) -> str | None:
        # §六：queue_position 是唯一执行顺序事实源（priority 不参与排序）
        with self._session_factory() as session:
            job = session.execute(
                select(Job).where(Job.status == "QUEUED")
                .order_by(Job.queue_position, Job.created_at)
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

        try:
            outcome = await self._execute_job(job_id)
        except asyncio.CancelledError:
            # 正常 shutdown（进程退出 / 停机超时）：绝不写 Job 终态——
            # 现场保持 RUNNING，交由下次启动恢复（§三十七）
            logger.info("Job %s 执行被取消（不写终态，交由启动恢复）", job_id)
            raise
        except Exception as error:
            # §0.1：代码级意外异常 → 当前 Job/Stage INTERRUPTED（保留恢复信息）+ 队列暂停，
            # 绝不继续领取下一个 Job，也绝不让 Job 停在 RUNNING
            logger.exception("Worker 内部异常（Job %s → INTERRUPTED，队列暂停）", job_id)
            self._worker_internal_error(job_id, error)
        else:
            self._finish_job(job_id, outcome)
        finally:
            self._current_job_id = None

    async def _execute_job(self, job_id: str) -> str:
        """按 Stage 顺序执行（Stage Gate 在此强制）；返回终态 outcome（不负责写 Job 终态）。"""
        for stage_id in self._load_stage_ids(job_id):
            # Stage 级边界（§七/§十九）：进入新 Stage 前检查暂停/取消
            with self._session_factory() as session:
                job = session.get(Job, job_id)
                stage = session.get(JobStage, stage_id)
                if job is None or stage is None:
                    return "FAILED"
                if job.cancel_requested:
                    self._cancel_remaining(session, job)
                    return "CANCELLED"
                if job.pause_requested:
                    job.status = "PAUSED"
                    job_service.record_event(session, job.id, "JOB_PAUSED")
                    session.commit()
                    return "PAUSED"
                stage_status = stage.status
            if stage_status == "COMPLETED":
                continue  # §八：绝不重新跑已经完成的 Stage
            if stage_status == "FAILED":
                return "FAILED"  # Stage Gate：FAILED 之后的后继 Stage 永不启动
            if stage_status in ("CANCELLED",):
                return "CANCELLED"

            result = await self._run_stage(job_id, stage_id)
            if result in ("SYSTEMIC", "FAILED"):
                return "FAILED"
            if result == "CANCELLED":
                return "CANCELLED"
            if result == "PAUSED":
                return "PAUSED"
            # COMPLETED → 允许启动下一 Stage
        return "COMPLETED"

    def _load_stage_ids(self, job_id: str) -> list[str]:
        with self._session_factory() as session:
            return list(session.execute(
                select(JobStage.id).where(JobStage.job_id == job_id).order_by(JobStage.stage_index)
            ).scalars())

    # ===== Stage 执行 =====
    async def _run_stage(self, job_id: str, stage_id: str) -> str:
        """执行一个 Stage 的全部未完成 StageItem；返回 COMPLETED / FAILED / CANCELLED / PAUSED / SYSTEMIC。"""
        with self._session_factory() as session:
            stage = session.get(JobStage, stage_id)
            if stage is None:
                return "FAILED"
            stage.status = "RUNNING"
            stage.started_at = stage.started_at or utc_now_iso()
            job_service.record_event(session, job_id, "STAGE_STARTED", payload={
                "stage_index": stage.stage_index, "module_id": stage.module_id,
                "module_version": stage.module_version,
            })
            session.commit()
            stage_item_ids = [item.id for item in session.execute(
                select(JobStageItem).where(JobStageItem.job_stage_id == stage_id)
                .order_by(JobStageItem.item_index)
            ).scalars()]

        failed_any = False
        for stage_item_id in stage_item_ids:
            # StageItem 边界检查（§七）：暂停/取消只发生在边界，不强杀当前执行
            with self._session_factory() as session:
                job = session.get(Job, job_id)
                stage = session.get(JobStage, stage_id)
                stage_item = session.get(JobStageItem, stage_item_id)
                if job is None or stage is None or stage_item is None:
                    return "FAILED"
                if stage_item.status != "QUEUED":
                    if stage_item.status == "FAILED":
                        failed_any = True
                    continue  # 已完成/已取消的 StageItem 绝不重跑（§八）
                if job.cancel_requested:
                    self._cancel_remaining(session, job)
                    return "CANCELLED"
                if job.pause_requested:
                    job.status = "PAUSED"
                    job_service.record_event(session, job.id, "JOB_PAUSED")
                    session.commit()
                    return "PAUSED"

            result = await self._run_stage_item(job_id, stage_id, stage_item_id)
            if result == "SYSTEMIC":
                return "SYSTEMIC"
            if result == "CANCELLED":
                with self._session_factory() as session:
                    job = session.get(Job, job_id)
                    if job is not None:
                        self._cancel_remaining(session, job)
                return "CANCELLED"
            if result == "FAILED":
                # 非系统性失败：继续本 Stage 剩余项（Phase 2 语义），但绝不进入下一 Stage
                failed_any = True

        return self._settle_stage(job_id, stage_id, failed_any)

    def _settle_stage(self, job_id: str, stage_id: str, failed_any: bool) -> str:
        """Stage 收尾：全部 COMPLETED → COMPLETED；任一 FAILED → FAILED（§六）。"""
        with self._session_factory() as session:
            stage = session.get(JobStage, stage_id)
            if stage is None:
                return "FAILED"
            completed = sum(1 for item in stage.stage_items if item.status == "COMPLETED")
            failed = sum(1 for item in stage.stage_items if item.status == "FAILED")
            stage.completed_count = completed
            if failed or failed_any:
                stage.status = "FAILED"
            elif stage.total_count == 0 or completed == stage.total_count:
                stage.status = "COMPLETED"
            else:
                stage.status = "FAILED"
            if stage.status in ("COMPLETED", "FAILED", "CANCELLED"):
                stage.finished_at = utc_now_iso()
            job_service.record_event(session, job_id, f"STAGE_{stage.status}", payload={
                "stage_index": stage.stage_index, "completed": completed, "total": stage.total_count,
            })
            session.commit()
            return stage.status

    # ===== StageItem 执行 =====
    async def _run_stage_item(self, job_id: str, stage_id: str, stage_item_id: str) -> str:
        """返回：COMPLETED / FAILED / CANCELLED / SYSTEMIC。"""
        with self._session_factory() as session:
            job = session.get(Job, job_id)
            stage = session.get(JobStage, stage_id)
            stage_item = session.get(JobStageItem, stage_item_id)
            if job is None or stage is None or stage_item is None:
                return "FAILED"
            seed = self._seed_for(job, stage)
            timeout_seconds = self._stage_timeout_for(stage)
            if stage_item.input_image_id is None and stage.stage_index > 0:
                # 图片流转：上一 Stage 同槽位的输出即本 Stage 的输入
                stage_item.input_image_id = self._previous_output_image_id(
                    session, job_id, stage.stage_index, stage_item.item_index
                )
            input_image_id = stage_item.input_image_id
            stage_item.status = "RUNNING"
            stage_item.started_at = utc_now_iso()
            stage_item.progress = 0.0
            job_item = session.get(JobItem, stage_item.job_item_id)
            if job_item is not None:
                job_item.status = "RUNNING"
                job_item.started_at = job_item.started_at or stage_item.started_at
                job_item.current_stage = stage.module_id
                if stage.stage_index == 0:
                    job_item.seed = seed
            job_service.record_event(session, job_id, "STAGE_ITEM_STARTED", item_id=stage_item.job_item_id, payload={
                "stage_index": stage.stage_index, "module_id": stage.module_id, "seed": seed,
            })
            session.commit()
            # 会话关闭后仅使用已加载的标量字段（expire_on_commit=False）

        # 构造引擎请求（模块知识在 WorkflowModule；Worker 只提供通用上下文，§三/§二十二）
        # 只有可分类的 EngineError 落 Item FAILED；其余代码级异常向上抛（§0.1 → 队列暂停）
        try:
            input_image = self._load_input_image(input_image_id) if input_image_id else None
            request = await self._pipeline.build_engine_request(
                job, stage, stage_item, seed, self._adapter, input_image=input_image,
            )
        except EngineError as error:
            return self._stage_item_failed(job_id, stage_item_id, error.error_type, error.message)

        # 提交（瞬态网络错误重试 ≤2，规范 §三十六）
        started = time.monotonic()
        engine_job_id: str | None = None
        attempt = 0
        while True:
            try:
                engine_job_id = await self._adapter.submit_job(request)
                break
            except EngineError as error:
                if is_systemic(error.error_type):
                    # 系统性（离线/绑定缺失/hash 不一致/工作流错误等）→ Job FAILED + 队列暂停
                    return self._systemic_failure(job_id, stage_item_id, error)
                attempt += 1
                if error.transient and attempt <= MAX_SUBMIT_RETRIES:
                    await asyncio.sleep(0.5 * attempt)
                    continue
                return self._stage_item_failed(job_id, stage_item_id, error.error_type, error.message)

        self._bind_engine_job(job_id, stage_item_id, engine_job_id)

        # 轮询进度（§十：执行总超时，绝不无限 RUNNING）
        cancel_sent = False
        while True:
            await asyncio.sleep(self._engine_poll)
            if timeout_seconds and (time.monotonic() - started) > timeout_seconds:
                try:
                    await self._adapter.cancel_job(engine_job_id)  # best-effort，异常必须隔离
                except Exception:
                    logger.warning("超时取消引擎任务失败（忽略）", exc_info=True)
                return self._stage_item_failed(
                    job_id, stage_item_id, "ENGINE_TIMEOUT",
                    f"StageItem 执行超过 {int(timeout_seconds)} 秒未完成",
                )
            with self._session_factory() as session:
                job = session.get(Job, job_id)
                if job is not None and job.cancel_requested and not cancel_sent:
                    # §九：取消请求必须异常隔离——失败不改变语义，
                    # 当前 StageItem 可继续完成，完成后由边界检查落 CANCELLED
                    cancel_sent = True
                    try:
                        await self._adapter.cancel_job(engine_job_id)
                    except Exception:
                        logger.warning("引擎取消请求失败（当前项完成后停止领取）", exc_info=True)
            try:
                status = await self._adapter.get_job_status(engine_job_id)
            except EngineError as error:
                if is_systemic(error.error_type):
                    return self._systemic_failure(job_id, stage_item_id, error)
                with self._session_factory() as session:
                    stage_item = session.get(JobStageItem, stage_item_id)
                    retry = False
                    if stage_item is not None:
                        stage_item.retry_count += 1
                        retry = error.transient and stage_item.retry_count <= MAX_SUBMIT_RETRIES
                    session.commit()
                if retry:
                    continue
                return self._stage_item_failed(job_id, stage_item_id, "ENGINE_NETWORK", error.message)

            self._update_stage_item_progress(job_id, stage_item_id, status)

            if status.state == "succeeded":
                # §一（P0）：Engine succeeded 只是必要条件——必须成功取回输出并导入 Studio Image
                # 才允许 COMPLETED；禁止出现 COMPLETED + output_image_id=null。
                try:
                    outputs = await self._adapter.get_job_outputs(engine_job_id)
                except EngineError as error:
                    return self._stage_item_failed(job_id, stage_item_id, error.error_type, error.message)
                if not outputs:
                    return self._stage_item_failed(job_id, stage_item_id, "OUTPUT_MISSING",
                                                   "引擎报告成功但没有输出文件")
                try:
                    image_ids = self._import_outputs(job_id, stage_item_id, outputs)
                except Exception as error:
                    logger.exception("导入引擎输出失败")
                    return self._stage_item_failed(job_id, stage_item_id, "STORAGE_ERROR",
                                                   f"导入引擎输出失败: {error}")
                if not image_ids:
                    return self._stage_item_failed(job_id, stage_item_id, "STORAGE_ERROR",
                                                   "输出未导入为 Studio Image（image_ids 为空）")
                self._stage_item_completed(job_id, stage_item_id, image_ids)
                return "COMPLETED"
            if status.state == "canceled":
                self._stage_item_cancelled(job_id, stage_item_id)
                return "CANCELLED"
            if status.state == "failed":
                error_type = status.error_type or classify_engine_message(status.message)
                if is_systemic(error_type):
                    return self._systemic_failure(
                        job_id, stage_item_id, EngineError(error_type, status.message or error_type)
                    )
                return self._stage_item_failed(job_id, stage_item_id, error_type, status.message or error_type)
            if status.state == "unknown":
                # 引擎不认识该任务（如重启后丢失）：按可恢复失败处理，不自动重试
                return self._stage_item_failed(job_id, stage_item_id, "UNKNOWN_ENGINE_ERROR",
                                               "engine lost track of job")

    # ===== StageItem 辅助 =====

    def _seed_for(self, job: Job, stage: JobStage) -> int:
        """§0.4：默认每张独立随机 Seed；固定 Seed 仅用于单张精确复现，且只作用于第一个 Stage。"""
        if stage.stage_index == 0:
            try:
                snapshot = json.loads(job.workbench_snapshot_json or "{}")
            except ValueError:
                snapshot = {}
            if snapshot.get("seed_mode") == "fixed" and snapshot.get("seed") is not None:
                return int(snapshot["seed"])
        return SYSTEM_RANDOM.randint(0, self._seed_upper)

    def _stage_timeout_for(self, stage: JobStage) -> float:
        try:
            config = json.loads(stage.config_json or "{}")
        except ValueError:
            config = {}
        value = config.get("execution_timeout")
        if value is None:
            return self._stage_timeout
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            return self._stage_timeout
        return timeout if timeout > 0 else self._stage_timeout

    @staticmethod
    def _previous_output_image_id(session: Session, job_id: str, stage_index: int, item_index: int) -> str | None:
        """图片流转：查上一 Stage 同槽位的 output_image_id。"""
        if stage_index <= 0:
            return None
        row = session.execute(
            select(JobStageItem.output_image_id)
            .join(JobStage, JobStage.id == JobStageItem.job_stage_id)
            .where(JobStage.job_id == job_id, JobStage.stage_index == stage_index - 1,
                   JobStageItem.item_index == item_index)
        ).scalars().first()
        return row

    def _load_input_image(self, image_id: str):
        if self._input_loader is None:
            raise EngineError("STORAGE_ERROR", "未配置输入图片加载器（input_loader）")
        try:
            image = self._input_loader(image_id)
        except EngineError:
            raise
        except Exception as error:
            raise EngineError("STORAGE_ERROR", f"读取输入图片失败: {error}") from error
        if image is None:
            raise EngineError("STORAGE_ERROR", f"输入图片不存在: {image_id}")
        return image

    def _bind_engine_job(self, job_id: str, stage_item_id: str, engine_job_id: str) -> None:
        with self._session_factory() as session:
            stage_item = session.get(JobStageItem, stage_item_id)
            if stage_item is not None:
                stage_item.engine_job_id = engine_job_id
                job_item = session.get(JobItem, stage_item.job_item_id)
                if job_item is not None:
                    job_item.engine_job_id = engine_job_id
            session.commit()

    def _update_stage_item_progress(self, job_id: str, stage_item_id: str, status) -> None:
        with self._session_factory() as session:
            stage_item = session.get(JobStageItem, stage_item_id)
            if stage_item is None:
                return
            if status.progress is not None:
                stage_item.progress = float(status.progress)
            stage_index = None
            stage = session.get(JobStage, stage_item.job_stage_id)
            if stage is not None:
                stage_index = stage.stage_index
            job_item = session.get(JobItem, stage_item.job_item_id)
            if job_item is not None:
                job_item.progress = stage_item.progress
            job_service.record_event(
                session, job_id, "ITEM_PROGRESS", item_id=stage_item.job_item_id,
                payload={"progress": stage_item.progress, "stage": status.stage,
                         "stage_index": stage_index},
            )
            session.commit()

    def _stage_item_completed(self, job_id: str, stage_item_id: str, image_ids: list[str]) -> None:
        """StageItem 完成：output_image_id 落库；槽位处于最后一个 Stage 时 JobItem 才 COMPLETED。"""
        with self._session_factory() as session:
            stage_item = session.get(JobStageItem, stage_item_id)
            if stage_item is None:
                return
            stage = session.get(JobStage, stage_item.job_stage_id)
            stage_item.status = "COMPLETED"
            stage_item.output_image_id = image_ids[0]
            stage_item.progress = 1.0
            stage_item.finished_at = utc_now_iso()
            if stage is not None:
                stage.completed_count = sum(1 for it in stage.stage_items if it.status == "COMPLETED")
            job_item = session.get(JobItem, stage_item.job_item_id)
            is_last_stage = self._is_last_stage(session, stage_item.job_stage_id)
            if job_item is not None:
                job_item.image_id = image_ids[0]
                job_item.progress = 1.0
                if is_last_stage:
                    job_item.status = "COMPLETED"
                    job_item.finished_at = utc_now_iso()
                    job_service.record_event(session, job_id, "ITEM_COMPLETED",
                                             item_id=job_item.id, payload={"image_ids": image_ids})
            job_service.record_event(session, job_id, "STAGE_ITEM_COMPLETED", item_id=stage_item.job_item_id,
                                     payload={"image_ids": image_ids,
                                              "stage_index": stage.stage_index if stage else None})
            job = session.get(Job, job_id)
            if job is not None:
                job.completed_count = sum(1 for it in job.items if it.status == "COMPLETED")
            session.commit()

    def _is_last_stage(self, session: Session, stage_id: str) -> bool:
        stage = session.get(JobStage, stage_id)
        if stage is None:
            return True
        max_index = session.execute(
            select(JobStage.stage_index).where(JobStage.job_id == stage.job_id)
            .order_by(JobStage.stage_index.desc())
        ).scalars().first()
        return stage.stage_index == max_index

    def _stage_item_cancelled(self, job_id: str, stage_item_id: str) -> None:
        with self._session_factory() as session:
            stage_item = session.get(JobStageItem, stage_item_id)
            if stage_item is None:
                return
            stage_item.status = "CANCELLED"
            stage_item.finished_at = utc_now_iso()
            job_service.record_event(session, job_id, "ITEM_CANCELLED", item_id=stage_item.job_item_id)
            session.commit()

    def _stage_item_failed(self, job_id: str, stage_item_id: str, error_type: str, message: str) -> str:
        with self._session_factory() as session:
            stage_item = session.get(JobStageItem, stage_item_id)
            if stage_item is None:
                return "FAILED"
            stage_item.status = "FAILED"
            stage_item.error_type = error_type
            stage_item.error_message = message
            stage_item.finished_at = utc_now_iso()
            stage = session.get(JobStage, stage_item.job_stage_id)
            job_item = session.get(JobItem, stage_item.job_item_id)
            if job_item is not None:
                job_item.status = "FAILED"
                job_item.error_type = error_type
                job_item.error_message = message
                job_item.finished_at = utc_now_iso()
            job_service.record_event(session, job_id, "ITEM_FAILED", item_id=stage_item.job_item_id, payload={
                "error_type": error_type, "message": message,
                "stage_index": stage.stage_index if stage else None,
            })
            session.commit()
        return "FAILED"

    def _systemic_failure(self, job_id: str, stage_item_id: str, error: EngineError) -> str:
        """系统性失败（规范 §二十一）：Job FAILED + 队列自动暂停；Stage FAILED，后续 Stage 不启动。"""
        with self._session_factory() as session:
            stage_item = session.get(JobStageItem, stage_item_id)
            stage = session.get(JobStage, stage_item.job_stage_id) if stage_item is not None else None
            if stage_item is not None:
                stage_item.status = "FAILED"
                stage_item.error_type = error.error_type
                stage_item.error_message = error.message
                stage_item.finished_at = utc_now_iso()
                job_item = session.get(JobItem, stage_item.job_item_id)
                if job_item is not None:
                    job_item.status = "FAILED"
                    job_item.error_type = error.error_type
                    job_item.error_message = error.message
                    job_item.finished_at = utc_now_iso()
            if stage is not None:
                stage.status = "FAILED"
                stage.completed_count = sum(1 for it in stage.stage_items if it.status == "COMPLETED")
                stage.finished_at = utc_now_iso()
                for remaining in stage.stage_items:
                    if remaining.status == "QUEUED":
                        remaining.status = "CANCELLED"
                        remaining.finished_at = utc_now_iso()
            job = session.get(Job, job_id)
            if job is not None:
                job.status = "FAILED"
                job.error_type = error.error_type
                job.error_message = error.message
                job.finished_at = utc_now_iso()
                job.completed_count = sum(1 for it in job.items if it.status == "COMPLETED")
                for queued_item in job.items:
                    if queued_item.status in ("QUEUED", "RUNNING"):
                        # RUNNING = 已完成前一 Stage、等待后续 Stage 的槽位：Job 终止后统一取消
                        queued_item.status = "CANCELLED"
                        queued_item.finished_at = utc_now_iso()
                job_service.record_event(session, job.id, "JOB_FAILED", payload={
                    "error_type": error.error_type, "message": error.message,
                })
            session.commit()
        self._pause_queue(f"{error.error_type}: {error.message}")
        return "SYSTEMIC"

    def _cancel_remaining(self, session: Session, job: Job) -> None:
        """取消：已生成的原图/高清图全部保留，只取消未完成部分（§七）。"""
        now = utc_now_iso()
        job.status = "CANCELLED"
        job.finished_at = now
        for stage in session.execute(select(JobStage).where(
            JobStage.job_id == job.id,
            JobStage.status.in_(("QUEUED", "RUNNING", "PAUSED", "INTERRUPTED")),
        )).scalars():
            stage.status = "CANCELLED"
            stage.finished_at = now
        for stage_item in session.execute(
            select(JobStageItem).join(JobStage, JobStage.id == JobStageItem.job_stage_id)
            .where(JobStage.job_id == job.id,
                   JobStageItem.status.in_(("QUEUED", "RUNNING", "INTERRUPTED")))
        ).scalars():
            stage_item.status = "CANCELLED"
            stage_item.finished_at = now
        for item in job.items:
            if item.status in ("QUEUED", "RUNNING", "INTERRUPTED"):
                item.status = "CANCELLED"
                item.finished_at = now
        job.completed_count = sum(1 for item in job.items if item.status == "COMPLETED")
        job_service.record_event(session, job.id, "JOB_CANCELLED")
        session.commit()

    def _finish_job(self, job_id: str, outcome: str) -> None:
        with self._session_factory() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            completed = sum(1 for item in job.items if item.status == "COMPLETED")
            job.completed_count = completed
            if job.status in ("CANCELLED", "PAUSED", "INTERRUPTED"):
                session.commit()  # 边界/系统性路径已落终态与事件
                return
            if job.status == "FAILED" and outcome in ("FAILED", "CANCELLED"):
                session.commit()  # _systemic_failure 已落终态，避免重复事件
                return
            if outcome == "FAILED":
                failed_items = [item for item in job.items if item.status == "FAILED"]
                job.status = "FAILED"
                if failed_items and not job.error_type:
                    job.error_type = failed_items[0].error_type or "UNKNOWN_ENGINE_ERROR"
                    job.error_message = failed_items[0].error_message or ""
                for item in job.items:
                    if item.status == "RUNNING":
                        # 已完成前一 Stage、等待后续 Stage 的槽位：Job FAILED 后不悬空
                        item.status = "CANCELLED"
                        item.finished_at = utc_now_iso()
            elif outcome == "CANCELLED":
                job.status = "CANCELLED"
            elif outcome == "PAUSED":
                job.status = "PAUSED"
            else:
                job.status = "COMPLETED" if completed == job.requested_count else "FAILED"
            if job.status in ("COMPLETED", "FAILED", "CANCELLED"):
                job.finished_at = utc_now_iso()
            job_service.record_event(session, job.id, f"JOB_{job.status}")
            session.commit()

    def _import_outputs(self, job_id: str, stage_item_id: str, outputs) -> list[str]:
        """导入引擎输出为 Studio Image；异常向上抛（调用方落 STORAGE_ERROR，§一）。"""
        if self._output_importer is None:
            raise RuntimeError("未配置 output_importer，无法导入引擎输出")
        with self._session_factory() as session:
            job = session.get(Job, job_id)
            stage_item = session.get(JobStageItem, stage_item_id)
            return list(self._output_importer(job, stage_item, outputs) or [])

    # ===== §0.1 Worker 内部异常 =====
    def _worker_internal_error(self, job_id: str, error: Exception) -> None:
        """代码级意外异常：当前 Job/Stage INTERRUPTED（保留恢复信息）+ 队列暂停（§0.1）。"""
        message = f"{type(error).__name__}: {error}"[:500]
        with self._session_factory() as session:
            job = session.get(Job, job_id)
            if job is not None:
                if job.status == "RUNNING":
                    job.status = "INTERRUPTED"
                job.error_type = "WORKER_INTERNAL_ERROR"
                job.error_message = message
                for stage in session.execute(select(JobStage).where(
                    JobStage.job_id == job.id, JobStage.status == "RUNNING"
                )).scalars():
                    stage.status = "INTERRUPTED"
                for stage_item in session.execute(
                    select(JobStageItem).join(JobStage, JobStage.id == JobStageItem.job_stage_id)
                    .where(JobStage.job_id == job.id, JobStageItem.status == "RUNNING")
                ).scalars():
                    stage_item.status = "INTERRUPTED"
                for item in job.items:
                    if item.status == "RUNNING":
                        item.status = "INTERRUPTED"
                job_service.record_event(session, job.id, "WORKER_INTERNAL_ERROR", payload={"message": message})
                session.commit()
        self._pause_queue(f"WORKER_INTERNAL_ERROR: {message}")

    # ===== 崩溃恢复（规范 §三十七、§三十八；Phase 3 §八/§九） =====
    async def recover_interrupted(self) -> list[str]:
        """启动时：RUNNING → INTERRUPTED，并按 StageItem 向引擎核对（§八）。

        确认成功则导入图片；引擎 history 丢失时按 Studio 自己的输出命名做文件级兜底（§九）。
        """
        with self._session_factory() as session:
            job_service.mark_interrupted_at_startup(session)
            # 全部 INTERRUPTED Job 都进入核对（含上次 Worker 内部异常留下的现场，§0.1）
            interrupted_ids = list(session.execute(
                select(Job.id).where(Job.status == "INTERRUPTED")
            ).scalars())
        recovered: list[str] = []
        for job_id in interrupted_ids:
            with self._session_factory() as session:
                rows = session.execute(
                    select(JobStageItem, JobStage)
                    .join(JobStage, JobStage.id == JobStageItem.job_stage_id)
                    .where(JobStage.job_id == job_id, JobStageItem.status == "INTERRUPTED")
                    .order_by(JobStage.stage_index, JobStageItem.item_index)
                ).all()
                targets = [
                    (stage_item.id, stage_item.engine_job_id, stage)
                    for stage_item, stage in rows
                ]
            recovered_in_job = 0
            for stage_item_id, engine_job_id, stage in targets:
                if await self._recover_stage_item(job_id, stage, stage_item_id, engine_job_id):
                    recovered.append(stage_item_id)
                    recovered_in_job += 1
            self._finalize_recovery(job_id, recovered_in_job)
        if recovered:
            logger.info("崩溃恢复：核对完成 %s 个 StageItem", len(recovered))
        return recovered

    async def _recover_stage_item(self, job_id: str, stage: JobStage, stage_item_id: str,
                                  engine_job_id: str | None) -> bool:
        outputs = []
        if engine_job_id:
            try:
                status = await self._adapter.get_job_status(engine_job_id)
            except Exception:
                status = None
            if status is not None and status.state == "succeeded":
                try:
                    outputs = await self._adapter.get_job_outputs(engine_job_id)
                except Exception:
                    outputs = []
        if not outputs:
            # §九：history 丢失（ComfyUI 重启）时，按 Studio 自己的命名规则核对输出文件
            outputs = self._scan_stage_outputs(job_id, stage, stage_item_id)
        if not outputs:
            return False  # 无法确认成功 → 保持 INTERRUPTED 可再核对
        try:
            image_ids = self._import_outputs(job_id, stage_item_id, outputs)
        except Exception:
            logger.warning("崩溃恢复导入输出失败（保持 INTERRUPTED）", exc_info=True)
            return False
        if not image_ids:
            return False  # §一：未导入 Studio Image 不得 COMPLETED
        self._stage_item_completed(job_id, stage_item_id, image_ids)
        with self._session_factory() as session:
            stage_item = session.get(JobStageItem, stage_item_id)
            if stage_item is not None:
                job_service.record_event(session, job_id, "ITEM_RECOVERED",
                                         item_id=stage_item.job_item_id, payload={"image_ids": image_ids})
            session.commit()
        return True

    def _scan_stage_outputs(self, job_id: str, stage: JobStage, stage_item_id: str) -> list:
        """文件级恢复兜底（§九）：只扫描 Studio 自己命名的输出（命名模板来自 provider binding）。"""
        scanner = getattr(self._adapter, "scan_stage_outputs", None)
        if scanner is None:
            return []
        ref = EngineBindingRef(
            module_id=stage.module_id,
            module_version=stage.module_version,
            provider=stage.provider or "unbound",
            binding_version=stage.binding_version or "v1",
            workflow_hash=stage.workflow_hash,
        )
        try:
            return list(scanner(ref, job_id=job_id, stage_index=stage.stage_index,
                                stage_item_id=stage_item_id) or [])
        except Exception:
            logger.debug("文件级恢复扫描不可用（忽略）", exc_info=True)
            return []

    def _finalize_recovery(self, job_id: str, recovered_count: int) -> None:
        """恢复核对后的终态归并（Phase 2.2 §2；Phase 3 按 Stage 归并）。"""
        with self._session_factory() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            completed = sum(1 for item in job.items if item.status == "COMPLETED")
            job.completed_count = completed
            stages = job.stages
            for stage in stages:
                stage.completed_count = sum(1 for item in stage.stage_items if item.status == "COMPLETED")
                if (stage.total_count == 0 or stage.completed_count == stage.total_count) \
                        and stage.status != "COMPLETED":
                    stage.status = "COMPLETED"
                    stage.finished_at = stage.finished_at or utc_now_iso()
            all_stages_completed = bool(stages) and all(stage.status == "COMPLETED" for stage in stages)
            if all_stages_completed and completed == job.requested_count:
                # 全部 Stage / Item 已恢复成功 → Job COMPLETED
                job.status = "COMPLETED"
                job.finished_at = utc_now_iso()
                job_service.record_event(session, job_id, "JOB_RECOVERED_COMPLETED",
                                         payload={"completed_count": completed})
            elif recovered_count:
                # 仍有 INTERRUPTED / QUEUED → 保持可恢复状态，只更新计数
                job_service.record_event(session, job_id, "JOB_UPDATED",
                                         payload={"status": job.status, "completed_count": completed})
            session.commit()