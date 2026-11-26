"""移动审核页的只读生图队列快照（mobile_generation_progress_v1 + queue status）。

只回答“现在跑到第几张、本段共几张、还剩几个生成段、当前是排队/生成/暂停”，
不暴露 Prompt、Job 控制或任何可写操作；控制面仍只在桌面 8000。
"""
from __future__ import annotations

from sqlalchemy import case, func, select, true
from sqlalchemy.orm import Session

from app.models.job import Job, JobItem, JobStageItem

ACTIVE_JOB_STATUSES = ("QUEUED", "RUNNING", "PAUSED")


def read_progress(session: Session) -> dict[str, int | str | None]:
    active = (Job.job_kind == "generate") & Job.status.in_(ACTIVE_JOB_STATUSES)
    counts = (
        select(
            func.sum(case((Job.status == "QUEUED", 1), else_=0)).label("queued_jobs"),
            func.sum(case((Job.status == "PAUSED", 1), else_=0)).label("paused_jobs"),
            func.sum(case((Job.status == "RUNNING", 1), else_=0)).label("running_jobs"),
        )
        .where(active)
        .subquery()
    )
    current = (
        select(
            (JobItem.item_index + 1).label("current_image"),
            Job.requested_count.label("images_in_segment"),
        )
        .select_from(Job)
        .join(JobItem, JobItem.job_id == Job.id)
        .join(JobStageItem, JobStageItem.job_item_id == JobItem.id)
        .where(
            Job.job_kind == "generate",
            Job.status == "RUNNING",
            JobStageItem.status == "RUNNING",
            JobItem.item_index >= 0,
            JobItem.item_index < Job.requested_count,
        )
        .order_by(JobStageItem.started_at.desc(), JobStageItem.id)
        .limit(1)
        .subquery()
    )
    # 父 JobItem 在 Stage 之间可能保持 RUNNING；只有 RUNNING 的 StageItem
    # 才代表当前执行槽位。队列计数与当前槽位在同一条只读查询里取回。
    snapshot = select(
        current.c.current_image,
        current.c.images_in_segment,
        counts.c.queued_jobs,
        counts.c.paused_jobs,
        counts.c.running_jobs,
    ).select_from(counts.outerjoin(current, true()))
    row = dict(session.execute(snapshot).mappings().one())
    queued = int(row["queued_jobs"] or 0)
    paused = int(row["paused_jobs"] or 0)
    running = int(row["running_jobs"] or 0)
    if running:
        # 生成中优先：即使正处于两张图之间的阶段间隙，也仍是“生成中”。
        active_status = "running"
    elif paused:
        active_status = "paused"
    elif queued:
        active_status = "queued"
    else:
        active_status = "none"
    return {
        "current_image": row["current_image"],
        "images_in_segment": row["images_in_segment"],
        "remaining_segments": queued + paused + running,
        "active_status": active_status,
        "queued_jobs": queued,
        "paused_jobs": paused,
    }
