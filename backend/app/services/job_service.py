"""JobService（Phase 2 规范 §十三、§十六-§二十、§五十七）。

- Job 创建**只能**发生在这里（Worker 不创建 Job）；
- 创建时固化 WorkbenchSnapshot + 最终 Prompt + 素材/尺寸/数量/Workflow 快照（§十）；
- client_request_id 幂等：同 (source, client_request_id) 重复提交返回原 Job（§十二）；
- 队列排序 = queue_position：normal 追加、next 插队到等待队列最前（§十五）；
- 只有 QUEUED Job 可排序（§十六）；
- 终态语义见 docs/JOB_STATE_MACHINE.md。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.ids import JOB, JOB_ITEM, JOB_STAGE, JOB_STAGE_ITEM, new_id
from app.core.timeutil import utc_now_iso
from app.engine.base import EngineError
from app.engine.errors import classify_engine_message
from app.models import (
    JOB_KINDS,
    JOB_SOURCES,
    JOB_STATUSES,
    Image,
    Job,
    JobEvent,
    JobItem,
    JobStage,
    JobStageItem,
)
from app.services.pipeline_validator import PipelineValidator
from app.services.prompt_composer import compose_structured, dumps_structured

TERMINAL_JOB_STATUSES = ("COMPLETED", "FAILED", "CANCELLED")
ACTIVE_JOB_STATUSES = ("QUEUED", "RUNNING", "PAUSED")
MAX_JOB_COUNT = 64
# §八：Prompt 长度上限（防止超大文本经 API/Agent 无限提交）
MAX_STRUCTURED_FIELD_CHARS = 2000
MAX_POSITIVE_PROMPT_CHARS = 10000
MAX_NEGATIVE_PROMPT_CHARS = 8000

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


def _workflow_snapshot_from_modules(modules: list[dict[str, Any]]) -> dict:
    """§四/§二十三：由真实模块身份列表构造 workflow_snapshot（唯一执行真源）。

    Phase 4 Task1/Task9：身份包含 workflow_hash + binding_hash 两个执行指纹，
    从历史恢复（打开工作台 / 配方）时携带完整身份即可固定原版本执行。
    Phase 5.1 Task1/Task3：config 进入快照（Workbench → Recipe → Job → JobStage.config_json 单链），
    禁止再经第二事实源传递模块参数。
    """
    normalized = [
        {
            "module_id": module.get("module_id"),
            "module_version": module.get("module_version"),
            "provider": module.get("provider"),
            "binding_version": module.get("binding_version"),
            "workflow_hash": module.get("workflow_hash"),
            "binding_hash": module.get("binding_hash"),
            "config": module.get("config") if isinstance(module.get("config"), dict) else {},
        }
        for module in modules
        if module.get("module_id")
    ]
    return {"modules": normalized}


def _merge_module_configs(
    modules: list[dict[str, Any]], workflow_modules: list[Any]
) -> list[dict[str, Any]]:
    """Task3：把工作台快照 workflow_modules[].config 合并进已解析的模块身份列表。

    模块参数只认 ``config`` 一个字段（正式契约 WorkflowModuleRefModel），
    resolved 身份（含双指纹）来自 API 层 resolve_workflow_modules；两处按 module_id 对齐。
    """
    requested: dict[str, dict[str, Any]] = {}
    for entry in workflow_modules or []:
        data = entry.model_dump() if isinstance(entry, BaseModel) else entry
        if not isinstance(data, dict):
            continue
        module_id = str(data.get("module_id") or "")
        config = data.get("config")
        if module_id and isinstance(config, dict):
            requested[module_id] = config
    merged: list[dict[str, Any]] = []
    for module in modules:
        module_id = str(module.get("module_id") or "")
        config = module.get("config")
        if not isinstance(config, dict):
            config = {}
        if module_id in requested:
            config = requested[module_id]
        merged.append({**module, "config": config})
    return merged


def _snapshot_input_images(snapshot: dict[str, Any]) -> list[tuple[str, str]]:
    """从 WorkbenchSnapshot 提取输入图片 (role, image_id) 对（Phase 5 §十；Phase 7 Task5 Slot 化）。

    - 角色/数量上限由模块声明的输入槽在 PipelineValidator 中校验（不再在 schema/服务层
      硬编码"只能 1 张 source"）；结构非法直接拒绝，禁止静默忽略；
    - 总数量上限与 WorkbenchSnapshotModel（max_length=4）保持一致。
    """
    refs = snapshot.get("input_images") or []
    if not isinstance(refs, list):
        raise ValidationError("input_images 必须为数组", code="WORKBENCH_INPUT_INVALID")
    pairs: list[tuple[str, str]] = []
    for ref in refs:
        if not isinstance(ref, dict) or not ref.get("image_id"):
            raise ValidationError("input_images 结构非法", code="WORKBENCH_INPUT_INVALID")
        role = str(ref.get("role") or "source")
        pairs.append((role, str(ref["image_id"])))
    if len(pairs) > 4:
        raise ValidationError("input_images 最多 4 张", code="WORKBENCH_INPUT_INVALID")
    return pairs


def _first_module_input_slots(modules: list[dict[str, Any]]):
    """解析首个模块声明的输入槽（Phase 7 Task5）。

    版本未注册时返回空（PipelineValidator 会另行以明确错误拒绝，这里不做兜底判断）。
    """
    from app.workflows.registry import default_registry

    if not modules:
        return ()
    first = modules[0]
    try:
        instance = default_registry().get(
            str(first.get("module_id") or ""), first.get("module_version")
        )
    except EngineError:
        return ()
    return instance.capabilities().input_slots


def _primary_input_image_id(pairs: list[tuple[str, str]], slots) -> str | None:
    """Stage0 链式主输入（StageItem.input_image_id）= 模块声明顺序中第一个有图的槽位。

    img2img/upscale：source；未来 reference 模块：其声明的首个槽位（如 face_reference）。
    槽位声明顺序即优先级；未声明任何槽位时回退到第一张输入图（会被 Validator 拒绝消费）。
    """
    for slot in slots:
        for role, image_id in pairs:
            if role == slot.role:
                return image_id
    return pairs[0][1] if pairs else None


def _materialize_stages(
    session: Session,
    job: Job,
    modules: list[dict[str, Any]],
    item_ids: list[str],
    *,
    stage_configs: list[dict[str, Any]] | None = None,
    input_image_ids: list[str | None] | None = None,
    reuse_plan: dict[tuple[int, int], JobStageItem] | None = None,
    parent_stages: dict[int, JobStage] | None = None,
) -> None:
    """把 workflow_snapshot.modules 物化为 JobStage + JobStageItem（§五）。

    - 每个模块 = 一个 Stage（stage_index = 顺序）；
    - 每个 Stage 为全部逻辑槽位创建 StageItem；
    - 处理型 Job（process）：第一（唯一）个 Stage 的 StageItem 预置 input_image_id（§二十一）；
    - config_json（Task3，Phase 5.1）：默认来自 module.config（唯一事实源）；
      stage_configs（内部/测试直调路径）与之合并（显式键优先，不丢模块参数）。
    - Stage-aware Resume（Phase 7 Task0）：``reuse_plan[(stage_index, item_index)]`` 命中的槽位
      直接物化为 COMPLETED，并继承父 StageItem 的 input/output/seed/engine 溯源，
      再写 ``reused_from_stage_item_id``；整段 Stage 全部复用 → Stage 直接 COMPLETED
      （Worker 按既有"绝不重跑已完成 Stage"语义跳过）。未复用槽位照常 QUEUED，
      Stage0 注入 input_image_ids[item_index]（复用槽位不注入、也不重新执行）。
    """
    configs = list(stage_configs or [])
    plan = reuse_plan or {}
    stages_by_index = parent_stages or {}
    for stage_index, module in enumerate(modules):
        module_config = module.get("config") if isinstance(module.get("config"), dict) else {}
        # 内部直调路径的 stage_configs 与模块 config 合并（不丢模块参数；显式键优先）
        override = configs[stage_index] if stage_index < len(configs) else {}
        stage_config = {**module_config, **(override if isinstance(override, dict) else {})}
        stage = JobStage(
            id=new_id(JOB_STAGE),
            job_id=job.id,
            stage_index=stage_index,
            module_id=str(module.get("module_id")),
            module_version=str(module.get("module_version") or "v1"),
            provider=module.get("provider"),
            binding_version=module.get("binding_version"),
            workflow_hash=module.get("workflow_hash"),
            binding_hash=module.get("binding_hash"),
            status="QUEUED",
            total_count=len(item_ids),
            completed_count=0,
            config_json=json.dumps(stage_config, ensure_ascii=False),
        )
        session.add(stage)
        session.flush()
        reused_count = 0
        for index, item_id in enumerate(item_ids):
            materialized_from = plan.get((stage_index, index))
            if materialized_from is not None:
                reused_count += 1
                session.add(JobStageItem(
                    id=new_id(JOB_STAGE_ITEM),
                    job_stage_id=stage.id,
                    job_item_id=item_id,
                    item_index=index,
                    input_image_id=materialized_from.input_image_id,
                    output_image_id=materialized_from.output_image_id,
                    seed=materialized_from.seed,
                    status="COMPLETED",
                    engine_job_id=materialized_from.engine_job_id,
                    progress=1.0,
                    started_at=materialized_from.started_at,
                    finished_at=materialized_from.finished_at,
                    reused_from_stage_item_id=materialized_from.id,
                ))
                continue
            input_image_id = None
            if input_image_ids is not None and stage_index == 0:
                input_image_id = input_image_ids[index]
            session.add(JobStageItem(
                id=new_id(JOB_STAGE_ITEM),
                job_stage_id=stage.id,
                job_item_id=item_id,
                item_index=index,
                input_image_id=input_image_id,
                status="QUEUED",
            ))
        if item_ids and reused_count == len(item_ids):
            # 整段复用：本 Stage 在子 Job 中从未真正执行，不重新分配任何资源
            stage.status = "COMPLETED"
            stage.completed_count = reused_count
            parent_stage = stages_by_index.get(stage_index)
            if parent_stage is not None and parent_stage.finished_at:
                stage.started_at = parent_stage.started_at
                stage.finished_at = parent_stage.finished_at
            else:
                now = utc_now_iso()
                stage.started_at = now
                stage.finished_at = now


def _request_fingerprint(
    *,
    job_kind: str,
    snapshot: dict[str, Any],
    input_image_ids: list[str],
    stage_configs: list[dict[str, Any]],
) -> str:
    """请求指纹（Phase 7 Task7）：判定同 (source, client_request_id) 下 payload 是否一致。

    只覆盖**请求语义**（job_kind + 工作台快照 + 显式输入/配置）：
    - queue_mode 不进入指纹（只影响排队位置，不影响任务内容；重放以原 Job 为准）；
    - 解析后的绑定身份（workflow_hash / binding_version 等）属于服务端派生，也不进入指纹。
    """
    canonical = json.dumps(
        {
            "job_kind": job_kind,
            "snapshot": snapshot,
            "input_image_ids": list(input_image_ids),
            "stage_configs": list(stage_configs),
        },
        sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _assert_idempotent_payload(existing: Job, fingerprint: str) -> None:
    """幂等命中时的 payload 一致性校验（Phase 7 Task7）。

    相同 key + 相同 payload → 返回原 Job（正常幂等重放）；
    相同 key + 不同 payload → IDEMPOTENCY_KEY_CONFLICT（绝不静默返回旧 Job）。
    历史 Job（fingerprint 为 NULL，本阶段之前创建）无法比对 → 保持旧兼容行为。
    """
    if existing.client_request_fingerprint and existing.client_request_fingerprint != fingerprint:
        raise ConflictError(
            "client_request_id 已用于不同的请求内容（幂等键冲突）",
            code="IDEMPOTENCY_KEY_CONFLICT",
        )


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


# ===== History（Phase 4 Task5/6：来源 = jobs；两级任务族归组） =====

HISTORY_BUCKETS: dict[str, tuple[str, ...] | None] = {
    "all": None,
    "active": ("QUEUED", "RUNNING", "PAUSED", "INTERRUPTED"),
    "completed": ("COMPLETED",),
    "failed": ("FAILED",),
    "cancelled": ("CANCELLED",),
}
MAX_HISTORY_WINDOW = 2000  # 本地工具规模上限；按创建时间倒序取窗口后归组


def list_history(
    session: Session,
    *,
    bucket: str = "all",
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """历史任务列表（Task5/6）：返回任务族列表 [(root_job, [resume_jobs...])] + 总族数。

    - 归组：沿 resume_of_job_id 向上找到最初 Job（root_job_id 为计算字段，不额外入库）；
    - 筛选：族内任一 Job 命中 bucket/source 即保留整族（避免续跑任务被显示成无关任务）；
    - 排序：族按族内最新 created_at 倒序；续跑任务族内按创建时间升序。
    """
    if bucket not in HISTORY_BUCKETS:
        raise ValidationError(f"非法历史筛选: {bucket}", code="HISTORY_BUCKET_INVALID")
    if source is not None and source not in JOB_SOURCES:
        raise ValidationError(f"非法任务来源: {source}", code="JOB_SOURCE_INVALID")
    if limit < 1 or limit > 200:
        raise ValidationError("limit 取值范围为 1-200")

    window = list(session.execute(
        select(Job).order_by(Job.created_at.desc()).limit(MAX_HISTORY_WINDOW)
    ).scalars())
    by_id = {job.id: job for job in window}

    def root_of(job: Job) -> Job:
        current = job
        seen: set[str] = set()
        while current.resume_of_job_id and current.resume_of_job_id not in seen:
            seen.add(current.id)
            parent = by_id.get(current.resume_of_job_id) or session.get(Job, current.resume_of_job_id)
            if parent is None:
                break
            current = parent
        return current

    families: dict[str, dict] = {}
    for job in window:
        root = root_of(job)
        family = families.setdefault(root.id, {"root": root, "resumes": []})
        if job.id != root.id:
            family["resumes"].append(job)

    statuses = HISTORY_BUCKETS[bucket]

    def matches(job: Job) -> bool:
        if source is not None and job.source != source:
            return False
        return statuses is None or job.status in statuses

    entries = [
        family for family in families.values()
        if matches(family["root"]) or any(matches(resume) for resume in family["resumes"])
    ]
    entries.sort(
        key=lambda family: max(
            [family["root"].created_at] + [r.created_at for r in family["resumes"]]
        ),
        reverse=True,
    )
    for family in entries:
        family["resumes"].sort(key=lambda job: job.created_at)
    total = len(entries)
    return entries[offset:offset + limit], total


def get_queue(session: Session) -> dict:
    """执行顺序的唯一事实源是 queue_position（§六：priority 不参与排序，仅保留作历史/显示）。"""
    running = session.execute(select(Job).where(Job.status == "RUNNING").order_by(Job.started_at)).scalars().first()
    queued = list(session.execute(
        select(Job).where(Job.status == "QUEUED").order_by(Job.queue_position, Job.created_at)
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
    workflow_modules: list[dict[str, Any]] | None = None,
    job_kind: str = "generate",
    input_image_ids: list[str] | None = None,
    stage_configs: list[dict[str, Any]] | None = None,
) -> tuple[Job, bool]:
    """创建 Job + N 个 JobItem + 物化 JobStage/JobStageItem（单事务，Phase 3 §五）。

    workflow_modules：真实执行身份列表（API 层经 resolve_workflow_modules 解析），
    缺省时为最小基础生成身份（直接调用 service 的测试/内部路径）。
    返回 (job, created)；幂等命中时 created=False：
    - 相同 (source, client_request_id) + 相同 payload → 返回原 Job（正常重放）；
    - 相同 key + 不同 payload → IDEMPOTENCY_KEY_CONFLICT（Phase 7 Task7）。
    """
    if source not in JOB_SOURCES:
        raise ValidationError(f"非法任务来源: {source}", code="JOB_SOURCE_INVALID")
    if queue_mode not in ("normal", "next"):
        raise ValidationError(f"非法队列模式: {queue_mode}", code="QUEUE_MODE_INVALID")
    if job_kind not in JOB_KINDS:
        raise ValidationError(f"非法任务类型: {job_kind}", code="JOB_KIND_INVALID")

    fingerprint = _request_fingerprint(
        job_kind=job_kind,
        snapshot=snapshot,
        input_image_ids=list(input_image_ids or []),
        stage_configs=list(stage_configs or []),
    )

    # 幂等（规范 §十二；Phase 7 Task7：payload 指纹判定冲突）
    if client_request_id:
        existing = session.execute(
            select(Job).where(Job.source == source, Job.client_request_id == client_request_id)
        ).scalars().first()
        if existing is not None:
            _assert_idempotent_payload(existing, fingerprint)
            return existing, False

    prompt_mode = snapshot.get("prompt_mode", "structured")
    if prompt_mode not in ("structured", "full"):
        raise ValidationError(f"非法 Prompt 模式: {prompt_mode}", code="PROMPT_MODE_INVALID")
    structured = snapshot.get("structured_prompt") or {}
    negative = snapshot.get("negative_prompt") or ""
    positive = compose_structured(structured) if prompt_mode == "structured" else (snapshot.get("full_prompt") or "")

    # §八：Prompt 长度上限（结构化逐字段 + 最终正向/负向）
    for field_name, field_value in structured.items():
        if isinstance(field_value, str) and len(field_value) > MAX_STRUCTURED_FIELD_CHARS:
            raise ValidationError(
                f"结构化 Prompt 字段 {field_name} 超长（≤{MAX_STRUCTURED_FIELD_CHARS} 字符）",
                code="PROMPT_TOO_LONG",
            )
    if len(positive) > MAX_POSITIVE_PROMPT_CHARS:
        raise ValidationError(f"正向 Prompt 超长（≤{MAX_POSITIVE_PROMPT_CHARS} 字符）", code="PROMPT_TOO_LONG")
    if len(negative) > MAX_NEGATIVE_PROMPT_CHARS:
        raise ValidationError(f"负向 Prompt 超长（≤{MAX_NEGATIVE_PROMPT_CHARS} 字符）", code="PROMPT_TOO_LONG")

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
    # Phase 3 §0.4：固定 Seed 仅用于精确复现单张；多张必须使用独立随机 Seed
    if seed_mode == "fixed" and count != 1:
        raise ValidationError(
            "固定 Seed 仅用于单张精确复现（count 必须为 1）；多张请使用随机 Seed",
            code="FIXED_SEED_SINGLE_ONLY",
        )

    modules: list[dict[str, Any]] = list(workflow_modules or [])
    if not modules:
        modules = [{
            "module_id": "basic_generate", "module_version": "v1",
            "provider": "unbound", "binding_version": "v1", "workflow_hash": None,
            "binding_hash": None,
        }]
    # Task3（Phase 5.1）：模块 config 从工作台快照合并进已解析身份（唯一事实源）
    modules = _merge_module_configs(modules, snapshot.get("workflow_modules") or [])

    # Phase 5 §十：从 WorkbenchSnapshot 冻结输入图片（Job 创建后切换工作台图片不影响本 Job）
    snapshot_inputs = _snapshot_input_images(snapshot)
    for _role, image_id in snapshot_inputs:
        if session.get(Image, image_id) is None:
            raise NotFoundError("输入图片不存在", code="IMAGE_NOT_FOUND")

    stage0_input_ids: list[str] | None = None
    input_roles: dict[str, int] = {}
    if job_kind == "process":
        # §二十/§二十一：处理型 Job 的输入 = 每 JobItem 一张已有图片（Pipeline 校验在 Validator）
        image_ids = list(input_image_ids or [])
        if len(image_ids) != count:
            raise ValidationError("处理型 Job 的图片数量与 count 不一致", code="PIPELINE_INVALID")
        # 快照携带输入图（如前端一并提交）时，必须与处理型输入一致，禁止两个事实源打架
        if snapshot_inputs and [image_id for _role, image_id in snapshot_inputs] != list(dict.fromkeys(image_ids)):
            raise ValidationError("快照输入图片与处理型输入不一致", code="PIPELINE_INVALID")
        stage0_input_ids = image_ids
        # 处理型 Job 的输入是**每 JobItem 一张**（不是 Job 级 N 张）：按"每个槽位 1 张 source"校验，
        # 否则图库多选高清会被误判为超出 input_slots.max_count（Phase 7 Task5）
        input_roles = {"source": 1} if image_ids else {}
    elif snapshot_inputs:
        # 生成型 Job：输入图片冻结到 Stage0 全部槽位；链式主输入 = 模块声明顺序中第一个有图的槽位
        slots = _first_module_input_slots(modules)
        primary = _primary_input_image_id(snapshot_inputs, slots)
        if primary is not None:
            stage0_input_ids = [primary] * count
        for role, _image_id in snapshot_inputs:
            input_roles[role] = input_roles.get(role, 0) + 1

    # Task4/Task5（Phase 5.1 + Phase 7）：Pipeline 输入合法性统一验证
    # （Job 创建前，禁止静默忽略输入图；Phase 7 Task5：按模块声明的输入槽校验角色/数量）
    PipelineValidator().validate(
        modules, job_kind=job_kind, has_input_image=bool(stage0_input_ids),
        input_roles=input_roles,
    )

    identity = modules[0]
    workflow_snapshot = _workflow_snapshot_from_modules(modules)
    # Phase 6 Task7：生成模式显式保存（text/image；旧调用方缺省 → None，由快照 input_images 语义兜底）
    generation_mode = snapshot.get("generation_mode")
    generation_settings = {
        "model_ref": None,
        "width": width,
        "height": height,
        "seed_mode": seed_mode,
        "seed": seed_value,
        "generation_mode": generation_mode if generation_mode in ("text", "image") else None,
        "params": {},
    }

    job = Job(
        id=new_id(JOB),
        source=source,
        client_request_id=client_request_id,
        # Phase 7 Task7：请求指纹只对携带幂等键的请求有意义
        client_request_fingerprint=fingerprint if client_request_id else None,
        status="QUEUED",
        job_kind=job_kind,
        prompt_mode=prompt_mode,
        positive_prompt_snapshot=positive,
        negative_prompt_snapshot=negative,
        structured_prompt_snapshot=dumps_structured(structured),
        workbench_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
        generation_settings_json=json.dumps(generation_settings, ensure_ascii=False),
        # §四：workflow_snapshot 必须同步"实际执行"的模块身份，不能出现 modules=[] 却执行了 basic_generate
        workflow_snapshot_json=json.dumps(workflow_snapshot, ensure_ascii=False),
        module_id=identity.get("module_id"),
        module_version=identity.get("module_version"),
        provider=identity.get("provider"),
        binding_version=identity.get("binding_version"),
        workflow_hash=identity.get("workflow_hash"),
        binding_hash=identity.get("binding_hash"),
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
        item_ids: list[str] = []
        for index in range(count):
            item_id = new_id(JOB_ITEM)
            item_ids.append(item_id)
            session.add(JobItem(id=item_id, job_id=job.id, item_index=index, status="QUEUED"))
        # §五：物化 JobStage / JobStageItem（Pipeline 从此刻起是唯一执行真源）
        _materialize_stages(
            session, job, modules, item_ids,
            stage_configs=stage_configs,
            input_image_ids=stage0_input_ids,
        )
        record_event(session, job.id, "JOB_CREATED", payload={
            "count": count, "queue_mode": queue_mode, "job_kind": job_kind,
            "modules": [m.get("module_id") for m in modules],
            # Phase 7 Task5：输入以 Slot 对（role, image_id）记录
            "input_images": [{"role": role, "image_id": image_id} for role, image_id in snapshot_inputs],
        })
        session.commit()
    except IntegrityError:
        session.rollback()
        # 并发幂等：另一个请求先创建了相同 client_request_id（Phase 7 Task7：同样校验指纹）
        if client_request_id:
            existing = session.execute(
                select(Job).where(Job.source == source, Job.client_request_id == client_request_id)
            ).scalars().first()
            if existing is not None:
                _assert_idempotent_payload(existing, fingerprint)
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


def resume_remaining(session: Session, original_job_id: str) -> tuple[Job, bool]:
    """取消/失败/中断后继续剩余图片（规范 §二十；Phase 7 Task0：真正 Stage-aware）。

    旧实现把整条 Pipeline 从 Stage 0 全部重跑（已完成的上游 Stage 被白白重算、
    img2img 输入图被重复消费）。现在的语义：

    - 对每个剩余（非 COMPLETED 的）槽位，逐 Stage 检查父 Job 的同槽位 StageItem：
      已 COMPLETED 且产出非空的上游 Stage **直接复用**（output/seed/engine 溯源继承，
      物化为子 Job 的 COMPLETED StageItem + reused_from_stage_item_id）；
    - 从第一个真正未完成的 Stage 才开始执行；
    - **只有真正重新执行的 Stage 才重新分配 Seed**：复用槽位保留原 Seed，绝不重算。

    原 Job 的快照与记录永不修改（只读原样取用后构造新的子 Job 快照）。
    """
    original = get_job(session, original_job_id)
    if original.status not in ("FAILED", "CANCELLED", "INTERRUPTED"):
        raise ValidationError(f"状态 {original.status} 不允许续跑剩余", code="INVALID_JOB_STATE")

    parent_items = list(session.execute(
        select(JobItem).where(JobItem.job_id == original.id).order_by(JobItem.item_index)
    ).scalars())
    incomplete_indexes = [item.item_index for item in parent_items if item.status != "COMPLETED"]
    remaining = len(incomplete_indexes)
    if remaining < 1:
        raise ValidationError("没有剩余图片可继续", code="NOTHING_TO_RESUME")

    # §五：续跑未完成图片必须使用新随机 Seed——不得复用父 Job 的 fixed seed；
    original_snapshot = json.loads(original.workbench_snapshot_json)
    snapshot = {
        **original_snapshot,
        "count": remaining,
        "seed_mode": "random",
        "seed": None,
    }
    settings_snapshot = json.loads(original.generation_settings_json or "{}")
    settings_snapshot.update({"seed_mode": "random", "seed": None})

    # §3（Phase 2.2）：Resume 必须完整继承 Parent 的 Workflow 身份（快照 + 全部列），
    # 不得读取当前 module_identity 静默升级到新 Workflow 版本；
    # 若原 binding 已不存在，执行时由 Adapter 明确报 BINDING_NOT_FOUND。
    resume_module_ids = json.loads(original.workflow_snapshot_json).get("modules") or []

    # ===== Phase 7 Task0：构建 Stage 级复用计划 =====
    parent_stages = list(session.execute(
        select(JobStage).where(JobStage.job_id == original.id).order_by(JobStage.stage_index)
    ).scalars())
    parent_item_index_by_id = {item.id: item.item_index for item in parent_items}
    parent_stage_items: dict[tuple[int, int], JobStageItem] = {}
    for stage_item, stage_index in session.execute(
        select(JobStageItem, JobStage.stage_index)
        .join(JobStage, JobStage.id == JobStageItem.job_stage_id)
        .where(JobStage.job_id == original.id)
    ).all():
        parent_index = parent_item_index_by_id.get(stage_item.job_item_id)
        if parent_index is not None:
            parent_stage_items[(stage_index, parent_index)] = stage_item

    # 只有"已 COMPLETED 且产出非空"的父 StageItem 才可复用（失败/取消/中断一律重执行）
    reuse_plan: dict[tuple[int, int], JobStageItem] = {}
    for stage in parent_stages:
        for child_index, parent_index in enumerate(incomplete_indexes):
            candidate = parent_stage_items.get((stage.stage_index, parent_index))
            if candidate is not None and candidate.status == "COMPLETED" and candidate.output_image_id:
                reuse_plan[(stage.stage_index, child_index)] = candidate

    # Stage0 输入：仅注入给"真正重新执行"的槽位；复用槽位不注入（不需要输入）
    fallback_inputs: list[str | None] = []
    parent_input_pairs: list[tuple[str, str]] = []
    if original.job_kind == "process":
        # 处理型 Job：剩余槽位沿用父 Job 的输入图片（按 item_index 对齐）
        inputs_by_index = {
            parent_index: item.input_image_id
            for (stage_index, parent_index), item in parent_stage_items.items() if stage_index == 0
        }
        fallback_inputs = [inputs_by_index.get(index) for index in incomplete_indexes]
    else:
        # 生成型 Job（Phase 5.1）：输入图必须从 Parent 快照重新冻结到全部剩余槽位，
        # 否则 img2img 续跑会静默丢失输入图（执行时才会炸）
        parent_input_pairs = _snapshot_input_images(original_snapshot)
        fallback_inputs = [parent_input_pairs[0][1] if parent_input_pairs else None] * remaining

    stage0_inputs: list[str | None] = []
    carried_inputs: list[str | None] = []
    for child_index, parent_index in enumerate(incomplete_indexes):
        parent_si = parent_stage_items.get((0, parent_index))
        value = (
            parent_si.input_image_id
            if parent_si is not None and parent_si.input_image_id
            else fallback_inputs[child_index]
        )
        # carried_inputs 表达"本 Job 的 Stage0 输入语义"（含复用槽位），用于管线合法性复核
        carried_inputs.append(value)
        stage0_inputs.append(None if (0, child_index) in reuse_plan else value)

    for image_id in stage0_inputs:
        if image_id is not None and session.get(Image, image_id) is None:
            raise NotFoundError("输入图片不存在，无法续跑", code="IMAGE_NOT_FOUND")

    # 输入角色（Phase 7 Task5）：处理型按"每个槽位 1 张 source"（每 JobItem 一张图）；
    # 生成型按父快照的 (role, image_id) 还原
    if original.job_kind == "process":
        input_roles: dict[str, int] = {"source": 1} if any(carried_inputs) else {}
    else:
        input_roles = {}
        for role, _image_id in parent_input_pairs:
            input_roles[role] = input_roles.get(role, 0) + 1

    # Task4/Task5（Phase 5.1 + Phase 7）：续跑同样在创建前验证 Pipeline（继承原身份的合法性复核）
    PipelineValidator().validate(
        resume_module_ids,
        job_kind=original.job_kind,
        has_input_image=any(carried_inputs),
        input_roles=input_roles,
    )

    job = Job(
        id=new_id(JOB),
        source="resume",
        status="QUEUED",
        job_kind=original.job_kind,
        prompt_mode=original.prompt_mode,
        positive_prompt_snapshot=original.positive_prompt_snapshot,
        negative_prompt_snapshot=original.negative_prompt_snapshot,
        structured_prompt_snapshot=original.structured_prompt_snapshot,
        workbench_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
        generation_settings_json=json.dumps(settings_snapshot, ensure_ascii=False),
        workflow_snapshot_json=original.workflow_snapshot_json,
        module_id=original.module_id,
        module_version=original.module_version,
        provider=original.provider,
        binding_version=original.binding_version,
        workflow_hash=original.workflow_hash,
        binding_hash=original.binding_hash,
        requested_count=remaining,
        priority=original.priority,
        resume_of_job_id=original.id,
        queue_position=next_queue_position(session),
    )
    try:
        session.add(job)
        session.flush()
        item_ids = []
        for index in range(remaining):
            item_id = new_id(JOB_ITEM)
            item_ids.append(item_id)
            # 复用 Stage0 的槽位保留其真实 Seed（只有真正重新执行的 Stage 才分配新 Seed；
            # 未复用槽位 seed 为 NULL，由 Worker 执行 Stage0 时分配）
            reused_stage0 = reuse_plan.get((0, index))
            session.add(JobItem(
                id=item_id, job_id=job.id, item_index=index, status="QUEUED",
                seed=reused_stage0.seed if reused_stage0 is not None else None,
            ))
        # §二十三：续跑同样物化 Stage（继承原 Workflow 身份；已完成的 Stage 直接复用）
        _materialize_stages(
            session, job, resume_module_ids, item_ids,
            input_image_ids=stage0_inputs,
            reuse_plan=reuse_plan,
            parent_stages={stage.stage_index: stage for stage in parent_stages},
        )
        record_event(session, job.id, "JOB_CREATED", payload={
            "count": remaining, "resume_of": original.id,
            "reused_stage_items": len(reuse_plan),
        })
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ConflictError("任务创建冲突，请重试", code="JOB_CREATE_CONFLICT")
    except Exception:
        session.rollback()
        raise
    return job, True


def reorder_queue(session: Session, ordered_job_ids: list[str]) -> list[Job]:
    """拖拽排序（§十六）：仅 QUEUED Job 可排序；payload 必须覆盖全部等待任务。

    §六：拖拽结果直接写入 queue_position（唯一执行顺序事实源），priority 不参与排序。
    """
    queued = list(session.execute(
        select(Job).where(Job.status == "QUEUED").order_by(Job.queue_position, Job.created_at)
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
        select(Job).where(Job.status == "QUEUED").order_by(Job.queue_position, Job.created_at)
    ).scalars())


# ===== 崩溃恢复（规范 §三十七） =====

def mark_interrupted_at_startup(session: Session) -> list[str]:
    """启动时把遗留 RUNNING Job/Stage/Item 转为 INTERRUPTED（不重新排队；Phase 3 §八）。"""
    interrupted_jobs: list[str] = []
    for job in session.execute(select(Job).where(Job.status == "RUNNING")).scalars():
        job.status = "INTERRUPTED"
        interrupted_jobs.append(job.id)
        for item in session.execute(select(JobItem).where(
            JobItem.job_id == job.id, JobItem.status == "RUNNING"
        )).scalars():
            item.status = "INTERRUPTED"
        for stage in session.execute(select(JobStage).where(
            JobStage.job_id == job.id, JobStage.status == "RUNNING"
        )).scalars():
            stage.status = "INTERRUPTED"
        for stage_item in session.execute(
            select(JobStageItem).join(JobStage, JobStage.id == JobStageItem.job_stage_id)
            .where(JobStage.job_id == job.id, JobStageItem.status == "RUNNING")
        ).scalars():
            stage_item.status = "INTERRUPTED"
        record_event(session, job.id, "JOB_INTERRUPTED", payload={"reason": "startup_recovery"})
    session.commit()
    for job_id in interrupted_jobs:
        _publish("JOB_UPDATED", job_id, payload={"status": "INTERRUPTED"})
    return interrupted_jobs


def classify_item_error(message: str) -> str:
    return classify_engine_message(message)
