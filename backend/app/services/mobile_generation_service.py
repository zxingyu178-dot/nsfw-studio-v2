"""移动审核页的只读生图队列快照（mobile_generation_progress_v1 + 队列状态）。

只回答“现在跑到第几张、本段共几张、还剩几个生成段、当前是排队/生成/暂停、
当前张完成到多少、用的是哪款底模”，不暴露 Prompt、Job 控制或任何可写操作；控制面仍只在桌面 8000。
"""
from __future__ import annotations

import json

from sqlalchemy import case, func, select, true
from sqlalchemy.orm import Session

from app.models.job import Job, JobItem, JobStageItem

ACTIVE_JOB_STATUSES = ("QUEUED", "RUNNING", "PAUSED")


def _snapshot_model(raw: str | None) -> str | None:
    """从运行中 Job 的 workflow 快照读取底模；旧任务/异常快照返回 None。"""
    try:
        snapshot = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return None
    modules = snapshot.get("modules") if isinstance(snapshot, dict) else None
    if not isinstance(modules, list) or not modules or not isinstance(modules[0], dict):
        return None
    config = modules[0].get("config")
    model = config.get("model") if isinstance(config, dict) else None
    return model.strip() if isinstance(model, str) and model.strip() else None


def read_progress(session: Session) -> dict[str, int | float | str | None]:
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
            JobStageItem.progress.label("current_progress"),
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
    # 运行中 Job 的底模：阶段间隙没有 RUNNING StageItem 时仍能继续显示，模型在 Job 内不变。
    running_job = (
        select(Job.workflow_snapshot_json.label("workflow_snapshot"))
        .where(Job.job_kind == "generate", Job.status == "RUNNING")
        .order_by(Job.started_at.desc(), Job.id)
        .limit(1)
        .subquery()
    )
    # 父 JobItem 在 Stage 之间可能保持 RUNNING；只有 RUNNING 的 StageItem
    # 才代表当前执行槽位。队列计数与当前槽位在同一条只读查询里取回。
    snapshot = select(
        current.c.current_image,
        current.c.images_in_segment,
        current.c.current_progress,
        counts.c.queued_jobs,
        counts.c.paused_jobs,
        counts.c.running_jobs,
        running_job.c.workflow_snapshot,
    ).select_from(counts.outerjoin(current, true()).outerjoin(running_job, true()))
    row = dict(session.execute(snapshot).mappings().one())
    queued = int(row["queued_jobs"] or 0)
    paused = int(row["paused_jobs"] or 0)
    running = int(row["running_jobs"] or 0)
    item_progress = row["current_progress"]
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
        # 当前张的采样进度（0..1）；阶段间隙或旧任务没有值时返回 null。
        "current_progress": (
            max(0.0, min(1.0, float(item_progress)))
            if item_progress is not None else None
        ),
        # 运行中任务的底模；排队/空闲/旧任务为 null，移动端据此隐藏底模行。
        "model": _snapshot_model(row["workflow_snapshot"]),
    }
