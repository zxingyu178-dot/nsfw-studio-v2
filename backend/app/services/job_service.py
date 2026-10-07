"""JobService（Phase 2 规范 §十三、§十六-§二十、§五十七）。

- Job 创建**只能**发生在这里（Worker 不创建 Job）；
- 创建时固化 WorkbenchSnapshot + 最终 Prompt + 素材/尺寸/数量/Workflow 快照（§十）；
- client_request_id 幂等：同 (source, client_request_id) 重复提交返回原 Job（§十二）；
- 队列排序 = queue_position：normal 追加、next 插队到等待队列最前（§十五）；
- 只有 QUEUED Job 可排序（§十六）；
- 终态语义见 docs/JOB_STATE_MACHINE.md。
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.ids import JOB, JOB_ITEM, new_id
from app.core.timeutil import utc_now_iso
from app.engine.errors import classify_engine_message
from app.models import JOB_SOURCES, JOB_STATUSES, Job, JobEvent, JobItem
from app.services.prompt_composer import compose_structured, dumps_structured

TERMINAL_JOB_STATUSES = ("COMPLETED", "FAILED", "CANCELLED")
ACTIVE_JOB_STATUSES = ("QUEUED", "RUNNING", "PAUSED")
MAX_JOB_COUNT = 64

_EVENT_BROKER = None  # 由 main.py 注入（进程内单例），避免循环依赖


def set_event_broker(broker) -> None:
    global _EVENT_BROKER
    _EVENT_BROKER = broker


def _publish(event_type: str, job_id: str, *, item_id: str | None = None, payload: dict | None = None) -> None:
    if _EVENT_BROKER is not None:
        _EVENT_BROKER.publish({
            "type": event_type,
            "job_id": job_id,
            "item_id": item_id,
            "payload": payload or {},
            "time": utc_now_iso(),
        })


def record_event(session: Session, job_id: str, event_type: str, *, item_id: str | None = None, payload: dict | None = None) -> None:
    session.add(JobEvent(job_id=job_id, job_item_id=item_id, event_type=event_type,
                         payload_json=json.dumps(payload or {}, ensure_ascii=False)))
    _publish(event_type, job_id, item_id=item_id, payload=payload)


# ===== 查询 =====

def get_job(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise NotFoundError("任务不存在", code="JOB_NOT_FOUND")
    return job


def get_items(session: Session, job_id: str) -> list[JobItem]:
    return list(session.execute(
        select(JobItem).where(JobItem.job_id == job_id).order_by(JobItem.item_index)
    ).scalars())


def list_jobs(session: Session, *, status: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[Job], int]:
    if limit < 1 or limit > 200:
        raise ValidationError("limit 取值范围为 1-200")
    query = select(Job)
    if status is not None:
        if status not in JOB_STATUSES:
            raise ValidationError(f"非法任务状态: {status}", code="JOB_STATUS_INVALID")
        query = query.where(Job.status == status)
    total = session.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    items = list(session.execute(query.order_by(Job.created_at.desc()).limit(limit).offset(offset)).scalars())
    return items, int(total)


def get_queue(session: Session) -> dict:
    running = session.execute(select(Job).where(Job.status == "RUNNING").order_by(Job.started_at)).scalars().first()
    queued = list(session.execute(
        select(Job).where(Job.status == "QUEUED").order_by(Job.priority.desc(), Job.queue_position)
    ).scalars())
    paused = list(session.execute(select(Job).where(Job.status == "PAUSED")).scalars())
    return {"running": running, "queued": queued, "paused": paused}


def next_queue_position(session: Session) -> int:
    current_max = session.execute(
        select(func.max(Job.queue_position)).where(Job.status == "QUEUED")
    ).scalar_one()
    return (current_max or 0) + 1


# ===== 创建（幂等） =====

def create_job(
    session: Session,
    *,
    source: str,
    snapshot: dict[str, Any],
    client_request_id: str | None = None,
    queue_mode: str = "normal",
    module_identity: dict[str, str | None] | None = None,
) -> tuple[Job, bool]:
    """创建 Job + N 个 JobItem（单事务）。

    返回 (job, created)；幂等命中时 created=False。
    """
    if source not in JOB_SOURCES:
        raise ValidationError(f"非法任务来源: {source}", code="JOB_SOURCE_INVALID")
    if queue_mode not in ("normal", "next"):
        raise ValidationError(f"非法队列模式: {queue_mode}", code="QUEUE_MODE_INVALID")

    # 幂等（规范 §十二）
    if client_request_id:
        existing = session.execute(
            select(Job).where(Job.source == source, Job.client_request_id == client_request_id)
        ).scalars().first()
        if existing is not None:
            return existing, False

    prompt_mode = snapshot.get("prompt_mode", "structured")
    if prompt_mode not in ("structured", "full"):
        raise ValidationError(f"非法 Prompt 模式: {prompt_mode}", code="PROMPT_MODE_INVALID")
    structured = snapshot.get("structured_prompt") or {}
    negative = snapshot.get("negative_prompt") or ""
    positive = compose_structured(structured) if prompt_mode == "structured" else (snapshot.get("full_prompt") or "")

    settings_snapshot = snapshot.get("generation_settings") or {}
    try:
        width = int(snapshot.get("width", 1024))
        height = int(snapshot.get("height", 1024))
        count = int(snapshot.get("count", 1))
    except (TypeError, ValueError):
        raise ValidationError("尺寸/数量必须为整数", code="GENERATION_SETTINGS_INVALID") from None
    if width <= 0 or height <= 0:
        raise ValidationError("尺寸必须为正整数", code="GENERATION_SETTINGS_INVALID")
    if count < 1 or count > MAX_JOB_COUNT:
        raise ValidationError(f"数量取值范围为 1-{MAX_JOB_COUNT}", code="GENERATION_SETTINGS_INVALID")
    seed_mode = snapshot.get("seed_mode", "random")
    seed_value = snapshot.get("seed")
    if seed_mode not in ("random", "fixed"):
        raise ValidationError("seed_mode 仅支持 random/fixed", code="SEED_MODE_INVALID")
    if seed_mode == "fixed" and seed_value is None:
        raise ValidationError("固定 Seed 模式必须提供 seed", code="SEED_MODE_INVALID")

    identity = module_identity or {}
    generation_settings = {
        "model_ref": None,
        "width": width,
        "height": height,
        "seed_mode": seed_mode,
        "seed": seed_value,
        "params": {},
    }

    job = Job(
        id=new_id(JOB),
        source=source,
        client_request_id=client_request_id,
        status="QUEUED",
        prompt_mode=prompt_mode,
        positive_prompt_snapshot=positive,
        negative_prompt_snapshot=negative,
        structured_prompt_snapshot=dumps_structured(structured),
        workbench_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
        generation_settings_json=json.dumps(generation_settings, ensure_ascii=False),
        workflow_snapshot_json=json.dumps({"modules": snapshot.get("workflow_modules", [])}, ensure_ascii=False),
        module_id=identity.get("module_id"),
        module_version=identity.get("module_version"),
        provider=identity.get("provider"),
        binding_version=identity.get("binding_version"),
        workflow_hash=identity.get("workflow_hash"),
        requested_count=count,
        priority=1 if queue_mode == "next" else 0,
    )
    if queue_mode == "next":
        # 插队到等待队列最前（规范 §十五）：现有 QUEUED 位置后移
        for queued in session.execute(select(Job).where(Job.status == "QUEUED")).scalars():
            queued.queue_position = (queued.queue_position or 0) + 1
        job.queue_position = 1
    else:
        job.queue_position = next_queue_position(session)

    try:
        session.add(job)
        session.flush()
        for index in range(count):
            session.add(JobItem(
                id=new_id(JOB_ITEM), job_id=job.id, item_index=index, status="QUEUED",
            ))
        record_event(session, job.id, "JOB_CREATED", payload={"count": count, "queue_mode": queue_mode})
        session.commit()
    except IntegrityError:
        session.rollback()
        # 并发幂等：另一个请求先创建了相同 client_request_id
        if client_request_id:
            existing = session.execute(
                select(Job).where(Job.source == source, Job.client_request_id == client_request_id)
            ).scalars().first()
            if existing is not None:
                return existing, False
        raise ConflictError("任务创建冲突，请重试", code="JOB_CREATE_CONFLICT")
    except Exception:
        session.rollback()
        raise
    return job, True


# ===== 状态操作 =====

def pause_job(session: Session, job_id: str) -> Job:
    """安全暂停（规范 §十七）：置 pause_requested，当前 Item 完成后由 Worker 落 PAUSED。"""
    job = get_job(session, job_id)
    if job.status not in ("QUEUED", "RUNNING"):
        raise ValidationError(f"状态 {job.status} 不允许暂停", code="INVALID_JOB_STATE")
    job.pause_requested = True
    if job.status == "QUEUED":
        # 尚未开始：直接落 PAUSED（无需经过 Worker）
        job.status = "PAUSED"
        record_event(session, job.id, "JOB_PAUSED")
    else:
        record_event(session, job.id, "JOB_PAUSE_REQUESTED")
    session.commit()
    _publish("JOB_UPDATED", job.id, payload={"status": job.status})
    return job


def resume_job(session: Session, job_id: str) -> Job:
    """继续暂停任务（规范 §十八）：PAUSED → QUEUED；已完成 Item 绝不重跑。"""
    job = get_job(session, job_id)
    if job.status != "PAUSED":
        raise ValidationError(f"状态 {job.status} 不允许继续", code="INVALID_JOB_STATE")
    job.pause_requested = False
    job.status = "QUEUED"
    job.queue_position = next_queue_position(session)
    record_event(session, job.id, "JOB_RESUMED")
    session.commit()
    _publish("JOB_UPDATED", job.id, payload={"status": job.status})
    return job


def cancel_job(session: Session, job_id: str) -> Job:
    """取消（规范 §十九）：终态 CANCELLED；QUEUED/PAUSED 立即取消，RUNNING 由 Worker 在边界处理。"""
    job = get_job(session, job_id)
    if job.status in TERMINAL_JOB_STATUSES:
        raise ValidationError(f"状态 {job.status} 不允许取消", code="INVALID_JOB_STATE")
    job.cancel_requested = True
    if job.status in ("QUEUED", "PAUSED"):
        job.status = "CANCELLED"
        job.finished_at = utc_now_iso()
        for item in session.execute(select(JobItem).where(
            JobItem.job_id == job.id, JobItem.status == "QUEUED"
        )).scalars():
            item.status = "CANCELLED"
            item.finished_at = utc_now_iso()
        record_event(session, job.id, "JOB_CANCELLED")
    else:
        record_event(session, job.id, "JOB_CANCEL_REQUESTED")
    session.commit()
    _publish("JOB_UPDATED", job.id, payload={"status": job.status})
    return job


def resume_remaining(session: Session, original_job_id: str, *, module_identity: dict[str, str | None] | None = None) -> tuple[Job, bool]:
    """取消/失败/中断后继续剩余图片（规范 §二十）：创建子 Job，只含未完成数量。"""
    original = get_job(session, original_job_id)
    if original.status not in ("FAILED", "CANCELLED", "INTERRUPTED"):
        raise ValidationError(f"状态 {original.status} 不允许续跑剩余", code="INVALID_JOB_STATE")

    completed = session.execute(
        select(func.count()).select_from(JobItem)
        .where(JobItem.job_id == original.id, JobItem.status == "COMPLETED")
    ).scalar_one()
    remaining = original.requested_count - completed
    if remaining < 1:
        raise ValidationError("没有剩余图片可继续", code="NOTHING_TO_RESUME")

    snapshot = json.loads(original.workbench_snapshot_json)
    job = Job(
        id=new_id(JOB),
        source="resume",
        status="QUEUED",
        prompt_mode=original.prompt_mode,
        positive_prompt_snapshot=original.positive_prompt_snapshot,
        negative_prompt_snapshot=original.negative_prompt_snapshot,
        structured_prompt_snapshot=original.structured_prompt_snapshot,
        workbench_snapshot_json=original.workbench_snapshot_json,
        generation_settings_json=original.generation_settings_json,
        workflow_snapshot_json=original.workflow_snapshot_json,
        module_id=original.module_id,
        module_version=original.module_version,
        provider=original.provider,
        binding_version=original.binding_version,
        workflow_hash=original.workflow_hash,
        requested_count=remaining,
        priority=original.priority,
        resume_of_job_id=original.id,
        queue_position=next_queue_position(session),
    )
    try:
        session.add(job)
        session.flush()
        for index in range(remaining):
            session.add(JobItem(id=new_id(JOB_ITEM), job_id=job.id, item_index=index, status="QUEUED"))
        record_event(session, job.id, "JOB_CREATED", payload={"count": remaining, "resume_of": original.id})
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ConflictError("任务创建冲突，请重试", code="JOB_CREATE_CONFLICT")
    except Exception:
        session.rollback()
        raise
    return job, True


def reorder_queue(session: Session, ordered_job_ids: list[str]) -> list[Job]:
    """拖拽排序（规范 §十六）：仅 QUEUED Job 可排序；payload 必须覆盖全部等待任务。"""
    queued = list(session.execute(
        select(Job).where(Job.status == "QUEUED").order_by(Job.priority.desc(), Job.queue_position)
    ).scalars())
    queued_ids = [job.id for job in queued]
    if set(ordered_job_ids) != set(queued_ids) or len(ordered_job_ids) != len(queued_ids):
        raise ValidationError("排序列表必须与当前等待任务一一对应", code="REORDER_INVALID")
    for position, job_id in enumerate(ordered_job_ids, start=1):
        job = next(job for job in queued if job.id == job_id)
        job.queue_position = position
    session.commit()
    for job in queued:
        _publish("JOB_UPDATED", job.id, payload={"status": job.status, "queue_position": job.queue_position})
    return list(session.execute(
        select(Job).where(Job.status == "QUEUED").order_by(Job.priority.desc(), Job.queue_position)
    ).scalars())


# ===== 崩溃恢复（规范 §三十七） =====

def mark_interrupted_at_startup(session: Session) -> list[str]:
    """启动时把遗留 RUNNING Job/Item 转为 INTERRUPTED（不重新排队）。"""
    interrupted_jobs: list[str] = []
    for job in session.execute(select(Job).where(Job.status == "RUNNING")).scalars():
        job.status = "INTERRUPTED"
        interrupted_jobs.append(job.id)
        for item in session.execute(select(JobItem).where(
            JobItem.job_id == job.id, JobItem.status == "RUNNING"
        )).scalars():
            item.status = "INTERRUPTED"
        record_event(session, job.id, "JOB_INTERRUPTED", payload={"reason": "startup_recovery"})
    session.commit()
    for job_id in interrupted_jobs:
        _publish("JOB_UPDATED", job_id, payload={"status": "INTERRUPTED"})
    return interrupted_jobs


def classify_item_error(message: str) -> str:
    return classify_engine_message(message)
