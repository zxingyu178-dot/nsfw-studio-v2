"""Jobs / Queue / SSE / Engine 状态 API（Phase 2A，规范 §二十四）。"""
from __future__ import annotations

import asyncio
import json
import shutil

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.config import Settings
from app.core.errors import ValidationError
from app.engine.base import EngineError
from app.engine.factory import module_identity
from app.schemas.job import (
    JobCreateRequest,
    JobListResponse,
    JobResponse,
    QueueReorderRequest,
    QueueResponse,
    job_response,
)
from app.services import job_service

router = APIRouter(tags=["jobs"])


def _module_identity(settings: Settings) -> dict:
    """模块身份（含 provider binding hash）；binding 缺失等引擎层错误转为可读 4xx。"""
    try:
        return module_identity(settings)
    except EngineError as error:
        raise ValidationError(error.message, code=error.error_type) from error


def _check_disk_space(request: Request) -> str:
    """磁盘空间检查（规范 §五十七）：严重不足拒绝新任务。"""
    settings: Settings = request.app.state.settings
    usage = shutil.disk_usage(settings.storage.data_root)
    free = usage.free
    if free < settings.storage.min_free_bytes_severe:
        raise ValidationError(
            f"磁盘空间严重不足（剩余 {free // (1024**3)} GB），已拒绝新任务，请清理 DataRoot",
            code="DISK_SPACE_CRITICAL",
        )
    if free < settings.storage.min_free_bytes_warning:
        return "warning"
    return "ok"


@router.post("/jobs", response_model=JobResponse, status_code=201, summary="创建生成任务（入队）")
def create_job(
    request: Request, body: JobCreateRequest, session: Session = Depends(get_session)
) -> JobResponse:
    disk = _check_disk_space(request)
    settings: Settings = request.app.state.settings
    job, created = job_service.create_job(
        session,
        source=body.source,
        client_request_id=body.client_request_id,
        snapshot=body.snapshot.model_dump(),
        queue_mode=body.queue_mode,
        module_identity=_module_identity(settings),
    )
    response = job_response(job)
    response.idempotent_replay = not created
    response.disk_space = disk
    return response


@router.get("/jobs", response_model=JobListResponse, summary="任务列表")
def list_jobs(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> JobListResponse:
    items, total = job_service.list_jobs(session, status=status, limit=limit, offset=offset)
    return JobListResponse(
        items=[job_response(job) for job in items], total=total, limit=limit, offset=offset
    )


@router.get("/jobs/{job_id}", response_model=JobResponse, summary="任务详情")
def get_job(job_id: str, session: Session = Depends(get_session)) -> JobResponse:
    job = job_service.get_job(session, job_id)
    return job_response(job)


@router.post("/jobs/{job_id}/pause", response_model=JobResponse, summary="安全暂停（当前图完成后暂停）")
def pause_job(job_id: str, session: Session = Depends(get_session)) -> JobResponse:
    return job_response(job_service.pause_job(session, job_id))


@router.post("/jobs/{job_id}/resume", response_model=JobResponse, summary="继续暂停任务")
def resume_job(job_id: str, session: Session = Depends(get_session)) -> JobResponse:
    return job_response(job_service.resume_job(session, job_id))


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse, summary="取消（终态；已完成图片保留）")
def cancel_job(job_id: str, session: Session = Depends(get_session)) -> JobResponse:
    return job_response(job_service.cancel_job(session, job_id))


@router.post("/jobs/{job_id}/resume-remaining", response_model=JobResponse, status_code=201,
             summary="继续剩余图片（创建子 Job，只含未完成数量）")
def resume_remaining(job_id: str, session: Session = Depends(get_session)) -> JobResponse:
    # §3（Phase 2.2）：续跑完整继承原 Job 的 Workflow 身份，不读取当前 settings（禁止静默升级）
    job, _ = job_service.resume_remaining(session, job_id)
    return job_response(job)


@router.get("/queue", response_model=QueueResponse, summary="当前队列（执行中/等待/暂停）")
def get_queue(request: Request, session: Session = Depends(get_session)) -> QueueResponse:
    queue = job_service.get_queue(session)
    worker = request.app.state.worker
    return QueueResponse(
        worker=worker.status() if worker else {"running": False},
        running=job_response(queue["running"]) if queue["running"] else None,
        queued=[job_response(job) for job in queue["queued"]],
        paused=[job_response(job) for job in queue["paused"]],
    )


@router.post("/queue/reorder", response_model=QueueResponse, summary="拖拽排序（仅等待任务）")
def reorder_queue(
    body: QueueReorderRequest, session: Session = Depends(get_session)
) -> QueueResponse:
    job_service.reorder_queue(session, body.ordered_job_ids)
    queue = job_service.get_queue(session)
    return QueueResponse(
        worker={"running": True},
        running=job_response(queue["running"]) if queue["running"] else None,
        queued=[job_response(job) for job in queue["queued"]],
        paused=[job_response(job) for job in queue["paused"]],
    )


@router.post("/queue/resume", summary="恢复队列（系统性失败暂停后，由用户确认恢复）")
def resume_queue(request: Request) -> dict:
    worker = request.app.state.worker
    worker.resume_queue()
    return {"queue_paused": False}


@router.get("/engine/status", summary="引擎健康状态（真实 Engine，独立于 Studio 状态）")
def engine_status(request: Request) -> dict:
    adapter = request.app.state.adapter
    # health 是轻量探测；同步端点中用独立事件循环执行
    result = asyncio.run(adapter.health())
    return {"online": result.online, "detail": result.detail,
            "engine_name": result.engine_name, "engine_version": result.engine_version}


@router.get("/events/jobs", summary="SSE：任务事件实时通知（数据库状态才是唯一事实源）")
async def job_events(request: Request) -> StreamingResponse:
    broker = request.app.state.events
    queue = broker.subscribe()

    async def event_stream():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            broker.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
