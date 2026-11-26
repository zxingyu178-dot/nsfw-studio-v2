"""移动审核页的只读生图队列快照（mobile_generation_progress_v1）。

只回答“现在跑到第几张、本段共几张、还剩几个生成段”，不暴露 Prompt、
Job 控制或任何可写操作；控制面仍只在桌面 8000。
"""
from __future__ import annotations

from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from app.models.job import Job, JobItem, JobStageItem


def read_progress(session: Session) -> dict[str, int | None]:
    remaining = (
        select(func.count(Job.id).label("remaining_segments"))
        .where(Job.job_kind == "generate", Job.status.in_(("QUEUED", "RUNNING", "PAUSED")))
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
    # 才代表当前执行槽位。与剩余段数在同一条只读查询里取回。
    snapshot = select(
        current.c.current_image,
        current.c.images_in_segment,
        remaining.c.remaining_segments,
    ).select_from(remaining.outerjoin(current, true()))
    return dict(session.execute(snapshot).mappings().one())
