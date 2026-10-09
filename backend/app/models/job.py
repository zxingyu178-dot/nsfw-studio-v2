"""Job / JobItem / JobEvent 模型（Phase 2A）。

状态机见 docs/JOB_STATE_MACHINE.md；快照原则见规范 §十。
JobItem.image_id 存 Image ID（0006 迁移建 images 表后由应用层关联，不加 FK 避免跨迁移环）。
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utc_now_iso
from app.database.base import Base

JOB_STATUSES = ("QUEUED", "RUNNING", "PAUSED", "INTERRUPTED", "COMPLETED", "FAILED", "CANCELLED")
JOB_ITEM_STATUSES = ("QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED")
JOB_SOURCES = ("web", "resume", "agent", "doubao")
# Phase 3：generate = 生成流水线（basic[+upscale]）；process = 处理型（图库高清等）
JOB_KINDS = ("generate", "process")
STAGE_STATUSES = ("QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("uq_jobs_client_request", "source", "client_request_id", unique=True,
              sqlite_where=text("client_request_id IS NOT NULL")),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    client_request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Phase 7 Task7：请求指纹（幂等键冲突判定）——相同 (source, client_request_id) 但
    # payload 不同时必须 IDEMPOTENCY_KEY_CONFLICT，而不是静默返回旧 Job。
    client_request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED")

    prompt_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    positive_prompt_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    negative_prompt_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    structured_prompt_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    workbench_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    generation_settings_json: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default='{"modules":[]}')

    # 实际执行身份（规范 §五十五）：保证 Workflow 修改后仍可溯源老 Job 用了什么
    module_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    module_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    binding_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    workflow_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Phase 4 Task1：binding.yaml 指纹（与 workflow_hash 并列，覆盖 inputs/defaults/save_image_* 等）
    binding_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    requested_count: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queue_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0 普通 / 1 优先(next)
    resume_of_job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    pause_requested: Mapped[bool] = mapped_column(nullable=False, default=False)
    cancel_requested: Mapped[bool] = mapped_column(nullable=False, default=False)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)
    started_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso, onupdate=utc_now_iso)

    # Phase 3：generate（生成流水线）/ process（图库高清等处理型）
    job_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="generate")

    items: Mapped[list["JobItem"]] = relationship(
        back_populates="job", order_by="JobItem.item_index", cascade="all, delete-orphan"
    )
    stages: Mapped[list["JobStage"]] = relationship(
        back_populates="job", order_by="JobStage.stage_index", cascade="all, delete-orphan"
    )


class JobItem(Base):
    __tablename__ = "job_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    item_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED")
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    engine_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress: Mapped[float | None] = mapped_column(nullable=True)
    image_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)
    started_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso, onupdate=utc_now_iso)

    job: Mapped[Job] = relationship(back_populates="items")


class JobStage(Base):
    """多阶段管线中的一个阶段（Phase 3 §一/§二）。

    每个 Stage 固化自己的 Workflow 身份（module/binding/hash），
    执行真源 = Stage + workflow_snapshot，而不是当前配置。
    """

    __tablename__ = "job_stages"
    __table_args__ = (
        Index("uq_job_stages_index", "job_id", "stage_index", unique=True),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    stage_index: Mapped[int] = mapped_column(Integer, nullable=False)

    module_id: Mapped[str] = mapped_column(String(64), nullable=False)
    module_version: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    binding_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    workflow_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    binding_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED")
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)
    started_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso, onupdate=utc_now_iso)

    job: Mapped[Job] = relationship(back_populates="stages")
    stage_items: Mapped[list["JobStageItem"]] = relationship(
        back_populates="stage", order_by="JobStageItem.item_index", cascade="all, delete-orphan"
    )


class JobStageItem(Base):
    """一个逻辑图片槽位在某个 Stage 的实际执行记录（Phase 3 §三）。

    input_image_id / output_image_id 表达图片流转；engine_job_id 用于崩溃恢复核对。
    """

    __tablename__ = "job_stage_items"
    __table_args__ = (
        Index("idx_stage_items_stage", "job_stage_id"),
        Index("idx_stage_items_item", "job_item_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_stage_id: Mapped[str] = mapped_column(ForeignKey("job_stages.id"), nullable=False)
    job_item_id: Mapped[str] = mapped_column(ForeignKey("job_items.id"), nullable=False)
    item_index: Mapped[int] = mapped_column(Integer, nullable=False)

    input_image_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_image_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Phase 4 Task3：本 StageItem 实际使用的 Seed（uses_seed=false 的 Stage 必须为 NULL）
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Phase 7 Task0：Stage-aware Resume 溯源——本 StageItem 复用自父 Job 的哪个 StageItem
    # （仅 COMPLETED/复用的物化项非空；真正重新执行的项永远为 NULL）
    reused_from_stage_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED")
    engine_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    progress: Mapped[float | None] = mapped_column(nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)
    started_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso, onupdate=utc_now_iso)

    stage: Mapped[JobStage] = relationship(back_populates="stage_items")
    job_item: Mapped[JobItem] = relationship()


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    job_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)
