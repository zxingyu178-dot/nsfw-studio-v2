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
from app.core.ids import JOB, JOB_ITEM, JOB_STAGE, JOB_STAGE_ITEM, new_id
from app.core.timeutil import utc_now_iso
from app.engine.errors import classify_engine_message
from app.models import (
    JOB_KINDS,
    JOB_SOURCES,
    JOB_STATUSES,
    Job,
    JobEvent,
    JobItem,
    JobStage,
    JobStageItem,
)
from app.services.prompt_composer import compose_structured, dumps_structured
from app.workflows.registry import default_registry

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
    """§四/§二十三：由真实模块身份列表构造 workflow_snapshot（唯一执行真源）。"""
    normalized = [
        {
            "module_id": module.get("module_id"),
            "module_version": module.get("module_version"),
            "provider": module.get("provider"),
            "binding_version": module.get("binding_version"),
            "workflow_hash": module.get("workflow_hash"),
        }
        for module in modules
        if module.get("module_id")
    ]
    return {"modules": normalized}


def _materialize_stages(
    session: Session,
    job: Job,
    modules: list[dict[str, Any]],
    item_ids: list[str],
    *,
    stage_configs: list[dict[str, Any]] | None = None,
    input_image_ids: list[str] | None = None,
) -> None:
    """把 workflow_snapshot.modules 物化为 JobStage + JobStageItem（§五）。

    - 每个模块 = 一个 Stage（stage_index = 顺序）；
    - 每个 Stage 为全部逻辑槽位创建 StageItem；
    - 处理型 Job（process）：第一（唯一）个 Stage 的 StageItem 预置 input_image_id（§二十一）。
    """
    configs = list(stage_configs or [])
    for stage_index, module in enumerate(modules):
        stage = JobStage(
            id=new_id(JOB_STAGE),
            job_id=job.id,
            stage_index=stage_index,
            module_id=str(module.get("module_id")),
            module_version=str(module.get("module_version") or "v1"),
            provider=module.get("provider"),
            binding_version=module.get("binding_version"),
            workflow_hash=module.get("workflow_hash"),
            status="QUEUED",
            total_count=len(item_ids),
            completed_count=0,
            config_json=json.dumps(configs[stage_index] if stage_index < len(configs) else {}, ensure_ascii=False),
        )
        session.add(stage)
        session.flush()
        for index, item_id in enumerate(item_ids):
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
    返回 (job, created)；幂等命中时 created=False。
    """
    if source not in JOB_SOURCES:
        raise ValidationError(f"非法任务来源: {source}", code="JOB_SOURCE_INVALID")
    if queue_mode not in ("normal", "next"):
        raise ValidationError(f"非法队列模式: {queue_mode}", code="QUEUE_MODE_INVALID")
    if job_kind not in JOB_KINDS:
        raise ValidationError(f"非法任务类型: {job_kind}", code="JOB_KIND_INVALID")

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
        }]
    # §三：Pipeline 的模块必须已注册（未知模块在创建期就被拒绝，而不是执行期才炸）
    registry = default_registry()
    for module in modules:
        module_id = str(module.get("module_id") or "")
        if not registry.has(module_id):
            raise ValidationError(f"WorkflowModule 未注册: {module_id}", code="WORKFLOW_ERROR")
    if job_kind == "process":
        # §二十/§二十一：处理型 Job 只跑处理模块，每个 JobItem 对应一张已有图片
        if [m.get("module_id") for m in modules] != ["upscale"]:
            raise ValidationError("处理型 Job 的 Pipeline 必须且只能是 upscale", code="PIPELINE_INVALID")
        image_ids = list(input_image_ids or [])
        if len(image_ids) != count:
            raise ValidationError("处理型 Job 的图片数量与 count 不一致", code="PIPELINE_INVALID")
    identity = modules[0]
    workflow_snapshot = _workflow_snapshot_from_modules(modules)
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
            input_image_ids=input_image_ids if job_kind == "process" else None,
        )
        record_event(session, job.id, "JOB_CREATED", payload={
            "count": count, "queue_mode": queue_mode, "job_kind": job_kind,
            "modules": [m.get("module_id") for m in modules],
        })
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


def resume_remaining(session: Session, original_job_id: str) -> tuple[Job, bool]:
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

    # §五：续跑未完成图片必须使用新随机 Seed——不得复用父 Job 的 fixed seed；
    # 原 Job 的快照永不修改（只读原样取用后构造新的子 Job 快照）。
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
    remaining_inputs: list[str] | None = None
    if original.job_kind == "process":
        # 处理型 Job：剩余槽位沿用父 Job 的输入图片（按 item_index 对齐）
        parent_stage_items = session.execute(
            select(JobStageItem).join(JobStage, JobStage.id == JobStageItem.job_stage_id)
            .where(JobStage.job_id == original.id, JobStage.stage_index == 0)
        ).scalars().all()
        incomplete_indexes = [
            item.item_index for item in session.execute(
                select(JobItem).where(JobItem.job_id == original.id, JobItem.status != "COMPLETED")
            ).scalars()
        ]
        inputs_by_index = {item.item_index: item.input_image_id for item in parent_stage_items}
        remaining_inputs = [inputs_by_index.get(index) for index in sorted(incomplete_indexes)]

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
            session.add(JobItem(id=item_id, job_id=job.id, item_index=index, status="QUEUED"))
        # §二十三：续跑同样物化 Stage（继承原 Workflow 身份，不由当前配置决定）
        _materialize_stages(session, job, resume_module_ids, item_ids, input_image_ids=remaining_inputs)
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
