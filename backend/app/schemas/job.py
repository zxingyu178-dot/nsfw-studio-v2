"""Job / Queue 相关出入参。"""
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models import Job, JobItem
from app.schemas.workbench import (
    StructuredPromptModel,
    WorkbenchSnapshotModel,
    structured_model_from_json,
)
import json


class JobCreateRequest(BaseModel):
    # Phase 2.1 §八：直接复用严格 WorkbenchSnapshotModel（宽高/数量/Seed 范围、
    # prompt_mode / selected_assets / workflow_modules 结构均由 schema 校验）
    snapshot: WorkbenchSnapshotModel
    client_request_id: str | None = Field(default=None, max_length=128)
    queue_mode: Literal["normal", "next"] = "normal"
    source: Literal["web", "resume", "agent", "doubao"] = "web"


class QueueReorderRequest(BaseModel):
    ordered_job_ids: list[str]


class JobItemResponse(BaseModel):
    id: str
    job_id: str
    item_index: int
    status: str
    seed: int | None
    engine_job_id: str | None
    current_stage: str | None
    progress: float | None
    image_id: str | None
    error_type: str | None
    error_message: str | None
    retry_count: int
    created_at: str
    started_at: str | None
    finished_at: str | None


class JobResponse(BaseModel):
    id: str
    source: str
    client_request_id: str | None
    status: str
    prompt_mode: str
    positive_prompt_snapshot: str
    negative_prompt_snapshot: str
    structured_prompt: StructuredPromptModel
    workbench_snapshot: dict[str, Any]
    generation_settings: dict[str, Any]
    workflow_snapshot: dict[str, Any]
    module_id: str | None
    module_version: str | None
    provider: str | None
    binding_version: str | None
    workflow_hash: str | None
    requested_count: int
    completed_count: int
    queue_position: int | None
    priority: int
    resume_of_job_id: str | None
    pause_requested: bool
    cancel_requested: bool
    error_type: str | None
    error_message: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    updated_at: str
    items: list[JobItemResponse]
    idempotent_replay: bool | None = None  # 仅创建响应携带：命中幂等时 True
    disk_space: str | None = None          # 仅创建响应携带：ok | warning


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    limit: int
    offset: int


class QueueResponse(BaseModel):
    worker: dict[str, Any]
    running: JobResponse | None
    queued: list[JobResponse]
    paused: list[JobResponse]


def job_item_response(item: JobItem) -> JobItemResponse:
    return JobItemResponse(
        id=item.id, job_id=item.job_id, item_index=item.item_index, status=item.status,
        seed=item.seed, engine_job_id=item.engine_job_id, current_stage=item.current_stage,
        progress=item.progress, image_id=item.image_id, error_type=item.error_type,
        error_message=item.error_message, retry_count=item.retry_count,
        created_at=item.created_at, started_at=item.started_at, finished_at=item.finished_at,
    )


def job_response(job: Job, items: list[JobItem] | None = None) -> JobResponse:
    return JobResponse(
        id=job.id, source=job.source, client_request_id=job.client_request_id, status=job.status,
        prompt_mode=job.prompt_mode,
        positive_prompt_snapshot=job.positive_prompt_snapshot,
        negative_prompt_snapshot=job.negative_prompt_snapshot,
        structured_prompt=structured_model_from_json(job.structured_prompt_snapshot),
        workbench_snapshot=json.loads(job.workbench_snapshot_json),
        generation_settings=json.loads(job.generation_settings_json),
        workflow_snapshot=json.loads(job.workflow_snapshot_json),
        module_id=job.module_id, module_version=job.module_version, provider=job.provider,
        binding_version=job.binding_version, workflow_hash=job.workflow_hash,
        requested_count=job.requested_count, completed_count=job.completed_count,
        queue_position=job.queue_position, priority=job.priority,
        resume_of_job_id=job.resume_of_job_id,
        pause_requested=job.pause_requested, cancel_requested=job.cancel_requested,
        error_type=job.error_type, error_message=job.error_message,
        created_at=job.created_at, started_at=job.started_at, finished_at=job.finished_at,
        updated_at=job.updated_at,
        items=[job_item_response(item) for item in (items if items is not None else job.items)],
    )
