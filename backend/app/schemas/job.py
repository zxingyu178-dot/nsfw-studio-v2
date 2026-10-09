"""Job / Queue 相关出入参。"""
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models import Job, JobItem, JobStage, JobStageItem
from app.schemas.workbench import (
    StructuredPromptModel,
    WorkbenchSnapshotModel,
    WorkflowSnapshotModel,
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


class JobStageItemResponse(BaseModel):
    """StageItem：一个逻辑图片槽位在某 Stage 的实际执行记录（§二十四；Phase 4 Task3 seed）。"""

    id: str
    job_stage_id: str
    job_item_id: str
    item_index: int
    input_image_id: str | None
    output_image_id: str | None
    seed: int | None
    # Phase 7 Task0：Stage-aware Resume 溯源（复用自父 Job 的 StageItem；重新执行项为 NULL）
    reused_from_stage_item_id: str | None
    status: str
    engine_job_id: str | None
    progress: float | None
    error_type: str | None
    error_message: str | None
    retry_count: int
    started_at: str | None
    finished_at: str | None


class JobStageResponse(BaseModel):
    """Stage：多阶段管线中的一个阶段（§二十四：module/status/total/completed/current_item/progress）。"""

    id: str
    stage_index: int
    module_id: str
    module_version: str
    provider: str | None
    binding_version: str | None
    workflow_hash: str | None
    binding_hash: str | None
    status: str
    total_count: int
    completed_count: int
    current_item: int | None
    progress: float | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    items: list[JobStageItemResponse]


class JobResponse(BaseModel):
    id: str
    source: str
    client_request_id: str | None
    status: str
    job_kind: str
    prompt_mode: str
    positive_prompt_snapshot: str
    negative_prompt_snapshot: str
    structured_prompt: StructuredPromptModel
    workbench_snapshot: dict[str, Any]
    generation_settings: dict[str, Any]
    # Phase 5.1 Task1：workflow_snapshot 使用正式模块契约（WorkflowModuleRefModel 列表）
    workflow_snapshot: WorkflowSnapshotModel
    module_id: str | None
    module_version: str | None
    provider: str | None
    binding_version: str | None
    workflow_hash: str | None
    binding_hash: str | None
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
    stages: list[JobStageResponse]
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


# ===== History（Phase 4 Task5/6：历史来源 = jobs，不另建 History 表；两级归组） =====

class HistoryEntryResponse(BaseModel):
    """历史任务族：原任务 + 其续跑任务（Task6 两级归组，不实现复杂树）。"""

    root_job_id: str
    root: JobResponse
    resumes: list[JobResponse]


class HistoryResponse(BaseModel):
    items: list[HistoryEntryResponse]
    total: int  # 命中筛选的任务族数量
    limit: int
    offset: int


def job_item_response(item: JobItem) -> JobItemResponse:
    return JobItemResponse(
        id=item.id, job_id=item.job_id, item_index=item.item_index, status=item.status,
        seed=item.seed, engine_job_id=item.engine_job_id, current_stage=item.current_stage,
        progress=item.progress, image_id=item.image_id, error_type=item.error_type,
        error_message=item.error_message, retry_count=item.retry_count,
        created_at=item.created_at, started_at=item.started_at, finished_at=item.finished_at,
    )


def _stage_item_response(stage_item: JobStageItem) -> JobStageItemResponse:
    return JobStageItemResponse(
        id=stage_item.id, job_stage_id=stage_item.job_stage_id, job_item_id=stage_item.job_item_id,
        item_index=stage_item.item_index, input_image_id=stage_item.input_image_id,
        output_image_id=stage_item.output_image_id, seed=stage_item.seed, status=stage_item.status,
        reused_from_stage_item_id=stage_item.reused_from_stage_item_id,
        engine_job_id=stage_item.engine_job_id, progress=stage_item.progress,
        error_type=stage_item.error_type, error_message=stage_item.error_message,
        retry_count=stage_item.retry_count, started_at=stage_item.started_at,
        finished_at=stage_item.finished_at,
    )


def job_stage_response(stage: JobStage) -> JobStageResponse:
    """Stage 响应：current_item = 当前 RUNNING 的槽位；progress = 含运行中部分分量的整体进度。"""
    items = list(stage.stage_items)
    running = next((item for item in items if item.status == "RUNNING"), None)
    total = stage.total_count
    if total:
        partial = float(running.progress) if (running is not None and running.progress is not None) else 0.0
        progress = min(1.0, (stage.completed_count + partial) / total)
    else:
        progress = None
    return JobStageResponse(
        id=stage.id, stage_index=stage.stage_index, module_id=stage.module_id,
        module_version=stage.module_version, provider=stage.provider,
        binding_version=stage.binding_version, workflow_hash=stage.workflow_hash,
        binding_hash=stage.binding_hash,
        status=stage.status, total_count=stage.total_count, completed_count=stage.completed_count,
        current_item=running.item_index if running is not None else None, progress=progress,
        created_at=stage.created_at, started_at=stage.started_at, finished_at=stage.finished_at,
        items=[_stage_item_response(item) for item in items],
    )


def job_response(job: Job, items: list[JobItem] | None = None) -> JobResponse:
    return JobResponse(
        id=job.id, source=job.source, client_request_id=job.client_request_id, status=job.status,
        job_kind=job.job_kind,
        prompt_mode=job.prompt_mode,
        positive_prompt_snapshot=job.positive_prompt_snapshot,
        negative_prompt_snapshot=job.negative_prompt_snapshot,
        structured_prompt=structured_model_from_json(job.structured_prompt_snapshot),
        workbench_snapshot=json.loads(job.workbench_snapshot_json),
        generation_settings=json.loads(job.generation_settings_json),
        workflow_snapshot=json.loads(job.workflow_snapshot_json),
        module_id=job.module_id, module_version=job.module_version, provider=job.provider,
        binding_version=job.binding_version, workflow_hash=job.workflow_hash,
        binding_hash=job.binding_hash,
        requested_count=job.requested_count, completed_count=job.completed_count,
        queue_position=job.queue_position, priority=job.priority,
        resume_of_job_id=job.resume_of_job_id,
        pause_requested=job.pause_requested, cancel_requested=job.cancel_requested,
        error_type=job.error_type, error_message=job.error_message,
        created_at=job.created_at, started_at=job.started_at, finished_at=job.finished_at,
        updated_at=job.updated_at,
        items=[job_item_response(item) for item in (items if items is not None else job.items)],
        stages=[job_stage_response(stage) for stage in job.stages],
    )
