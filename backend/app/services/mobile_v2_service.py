"""W3.1 Mobile Bridge V2 业务服务（复用现有图片 / Prompt / 评分 / 事件 / 回执）。

- feed 只读事件日志，事件 revision 使用数据库单调 seq（不再用毫秒时间戳）；
- 详情/提示词关联只认 Job 快照或 V1 导入元数据中的显式 ID，绝不按文本匹配；
- 单图 decision 与提示词评分走 ``mobile_mutation_service.atomic_write``：
  BEGIN IMMEDIATE → 设备复核 → 回执检查 → 业务+事件+回执同一事务。
"""
from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ValidationError
from app.models import Image, Job, Prompt, PromptEvaluation, PromptVersion
from app.models.mobile_review import ImageReviewSessionItem, MobileImageEvent, MobileImageSeen
from app.schemas.prompt import PromptEvaluationCreateRequest
from app.services import (
    image_event_service,
    image_review_session_service,
    image_service,
    mobile_mutation_service,
    prompt_image_service,
    prompt_scoring_service,
    prompt_service,
)

IMAGE_EVENT_TYPES = (
    image_event_service.EVENT_IMAGE_CREATED,
    image_event_service.EVENT_IMAGE_IMPORTED,
    image_event_service.EVENT_IMAGE_REVIEW_UPDATED,
    image_event_service.EVENT_IMAGE_FAVORITE_UPDATED,
    image_event_service.EVENT_IMAGE_METADATA_UPDATED,
    image_event_service.EVENT_IMAGE_REMOVED,
)

PROMPT_IMAGE_CURSOR_PREFIX = "mpi_"


class MobileReviewConflict(ConflictError):
    status_code = 409
    code = "REVIEW_CONFLICT"
    message = "图片已被其他设备修改，请刷新后重试"


class MobileCursorValidation(ValidationError):
    status_code = 422


def _json(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def _job_for_image(session: Session, image: Image) -> Job | None:
    return session.get(Job, image.job_id) if image.job_id else None


def _prompt_link(session: Session, image: Image, job: Job | None = None) -> tuple[str | None, str | None, str]:
    """可靠提示词关联：Job 快照 explicit ID 优先，其次 V1 导入元数据；不按正文匹配。"""
    prompt_id: str | None = None
    version_id: str | None = None
    job = job or _job_for_image(session, image)
    if job is not None:
        snapshot = _json(job.workbench_snapshot_json)
        candidate = snapshot.get("source_prompt_id")
        version_candidate = snapshot.get("source_prompt_version_id")
        if isinstance(candidate, str) and candidate:
            prompt_id = candidate
            version_id = version_candidate if isinstance(version_candidate, str) else None

    if prompt_id is None and image.source == "import":
        metadata = _json(image.metadata_json)
        v1_prompts = (metadata.get("v1_output") or {}).get("prompts") or []
        for item in v1_prompts:
            candidate = item.get("prompt_id") if isinstance(item, dict) else None
            if isinstance(candidate, str) and candidate:
                prompt_id = candidate
                version_candidate = item.get("version_id")
                version_id = version_candidate if isinstance(version_candidate, str) else None
                break

    if prompt_id is not None and session.get(Prompt, prompt_id) is None:
        prompt_id, version_id = None, None
    if prompt_id is not None and version_id is not None:
        version = session.get(PromptVersion, version_id)
        if version is None or version.prompt_id != prompt_id:
            version_id = None

    if prompt_id is None:
        return None, None, "UNLINKED"
    if version_id is None:
        return prompt_id, None, "UNRESOLVED"
    return prompt_id, version_id, "EXACT"


def _prompt_link_dto(session: Session, image: Image, job: Job | None = None) -> dict:
    prompt_id, version_id, link_state = _prompt_link(session, image, job)
    return {"prompt_id": prompt_id, "prompt_version_id": version_id, "link_state": link_state}


def image_summary(session: Session, image: Image, *, revision: int) -> dict[str, Any]:
    data = image_review_session_service._image_summary(image)
    data["revision"] = str(revision)
    data["prompt"] = _prompt_link_dto(session, image)
    return data


def feed(session: Session, *, cursor: str | None, limit: int) -> dict[str, Any]:
    limit = max(1, min(int(limit), 100))
    position = image_event_service.resolve_cursor(session, cursor)
    rows = list(session.scalars(
        select(MobileImageEvent)
        .where(
            MobileImageEvent.seq > position,
            MobileImageEvent.event_type.in_(IMAGE_EVENT_TYPES),
            MobileImageEvent.image_id.is_not(None),
        )
        .order_by(MobileImageEvent.seq.asc())
        .limit(limit + 1)
    ))
    has_more = len(rows) > limit
    selected = rows[:limit]
    items = []
    for event in selected:
        if event.event_type == image_event_service.EVENT_IMAGE_REMOVED:
            items.append({"image_id": event.image_id, "revision": str(event.seq), "event": "REMOVE"})
            continue
        image = session.get(Image, event.image_id)
        if image is None:
            items.append({"image_id": event.image_id, "revision": str(event.seq), "event": "REMOVE"})
            continue
        item = image_summary(session, image, revision=event.seq)
        item["event"] = "UPSERT"
        items.append(item)
    next_position = selected[-1].seq if selected else position
    return {
        "items": items,
        "next_cursor": image_event_service.encode_cursor(next_position),
        "has_more": has_more,
        "resumed": cursor is not None,
    }


def details(session: Session, image: Image) -> dict[str, Any]:
    job = _job_for_image(session, image)
    metadata = _json(image.metadata_json)
    prompt_id, version_id, link_state = _prompt_link(session, image, job)
    return {
        "image_id": image.id,
        "created_at": image.created_at,
        "generated_at": metadata.get("generated_at"),
        "width": image.width,
        "height": image.height,
        "positive_prompt": job.positive_prompt_snapshot if job is not None else None,
        "negative_prompt": job.negative_prompt_snapshot if job is not None else None,
        "prompt_id": prompt_id,
        "prompt_version_id": version_id,
        "link_state": link_state,
        "job_id": image.job_id,
        "module_id": job.module_id if job is not None else metadata.get("module_id"),
        "seed": image.seed,
        "model": None,
        "size_bytes": None,
        "mime": None,
        "updated_at": image.updated_at,
        "revision": str(image_event_service.latest_event_seq(session, image.id)),
    }


def _decision_result(session: Session, image: Image) -> dict[str, Any]:
    return {
        "image_id": image.id,
        "status": image.status,
        "is_favorite": bool(image.favorite),
        "updated_at": image.updated_at,
        "revision": str(image_event_service.latest_event_seq(session, image.id)),
    }


def _mark_seen(session: Session, device_id: str, image_id: str, *, seen: bool) -> None:
    row = session.get(MobileImageSeen, {"device_id": device_id, "image_id": image_id})
    if row is None:
        session.add(MobileImageSeen(device_id=device_id, image_id=image_id, seen=seen))
    else:
        row.seen = seen


STATUS_FOR_ACTION = {"KEEP": "KEEP", "REJECT": "REJECT", "RESET": "NEW"}


def decide(
    session: Session, *, device_id: str, image_id: str, action: str | None,
    favorite: bool | None, expected_updated_at: str, client_request_id: str,
) -> dict[str, Any]:
    if action is None and favorite is None:
        raise ValidationError("action 与 favorite 至少提供一个", code="REVIEW_MUTATION_EMPTY")
    payload = {
        "image_id": image_id,
        "action": action,
        "favorite": favorite,
        "expected_updated_at": expected_updated_at,
        "client_request_id": client_request_id,
    }
    # 旧分支 decide 的载荷不含 image_id；只用于迁移回执重放复核。
    legacy_payload = {
        "action": action,
        "favorite": favorite,
        "expected_updated_at": expected_updated_at,
        "client_request_id": client_request_id,
    }

    def apply() -> dict[str, Any]:
        image = image_service.get_image(session, image_id)
        if image.updated_at != expected_updated_at:
            raise MobileReviewConflict(details={
                "image": {
                    "image_id": image.id, "status": image.status,
                    "is_favorite": bool(image.favorite), "updated_at": image.updated_at,
                    "revision": str(image_event_service.latest_event_seq(session, image.id)),
                },
                "revision": str(image_event_service.latest_event_seq(session, image.id)),
            })
        status = STATUS_FOR_ACTION.get(action or "")
        changed = image_service.apply_review_fields(
            image, status=status, favorite=favorite, review_note=None,
        )
        image_event_service.record_review_change(
            session, image,
            review_changed=changed["review"], favorite_changed=changed["favorite"],
        )
        _mark_seen(
            session, device_id, image_id,
            seen=status != "NEW" or favorite is not None,
        )
        session.flush()
        return _decision_result(session, image)

    return mobile_mutation_service.atomic_write(
        session,
        device_id=device_id,
        operation=mobile_mutation_service.OP_IMAGE_DECISION,
        idempotency_key=client_request_id,
        payload=payload,
        action=apply,
        legacy_payload=legacy_payload,
    )


def _images_query(session: Session, prompt_id: str, version_id: str | None):
    prompt_service.get_prompt(session, prompt_id)
    if version_id is not None:
        prompt_service.get_version(session, prompt_id, version_id)
    links = prompt_image_service._prompt_image_links(prompt_id=prompt_id, version_id=version_id)
    return select(Image).where(Image.id.in_(select(links.c.image_id)))


def _evaluation_dto(evaluation: PromptEvaluation) -> dict[str, Any]:
    return {
        "evaluation_id": evaluation.id,
        "prompt_id": evaluation.prompt_id,
        "prompt_version_id": evaluation.prompt_version_id,
        "overall_score": evaluation.overall_score,
        "created_at": evaluation.created_at,
        "notes": evaluation.notes,
    }


def prompt_summary(session: Session, prompt_id: str, version_id: str | None) -> dict[str, Any]:
    query = _images_query(session, prompt_id, version_id)
    rows = select(PromptEvaluation).where(PromptEvaluation.prompt_id == prompt_id)
    latest = session.scalar(
        rows.order_by(PromptEvaluation.created_at.desc(), PromptEvaluation.id.desc()).limit(1)
    )
    if version_id is not None:
        version_latest = session.scalar(
            rows.where(PromptEvaluation.prompt_version_id == version_id)
            .order_by(PromptEvaluation.created_at.desc(), PromptEvaluation.id.desc()).limit(1)
        )
        count = session.scalar(
            select(func.count()).select_from(
                rows.where(PromptEvaluation.prompt_version_id == version_id).subquery()
            )
        )
    else:
        version_latest = None
        count = session.scalar(
            select(func.count()).select_from(
                rows.where(PromptEvaluation.prompt_version_id.is_(None)).subquery()
            )
        )

    known_seen = select(ImageReviewSessionItem.image_id).where(ImageReviewSessionItem.seen.is_(True))
    mobile_seen = select(MobileImageSeen.image_id).where(MobileImageSeen.seen.is_(True))
    seen_condition = (
        Image.reviewed_at.is_not(None)
        | Image.id.in_(known_seen)
        | Image.id.in_(mobile_seen)
    )
    image_ids = query.with_only_columns(Image.id).subquery()
    total, seen, keep, reject = session.execute(
        select(
            func.count(),
            func.coalesce(func.sum(seen_condition.cast(Integer)), 0),
            func.coalesce(func.sum((Image.status == "KEEP").cast(Integer)), 0),
            func.coalesce(func.sum((Image.status == "REJECT").cast(Integer)), 0),
        ).select_from(Image).where(Image.id.in_(select(image_ids.c.id)))
    ).one()

    has_new_samples = False
    if version_latest is not None:
        has_new_samples = bool(session.scalar(
            select(func.count()).select_from(Image).where(
                Image.id.in_(select(image_ids.c.id)),
                Image.created_at > version_latest.created_at,
            )
        ))
    return {
        "prompt_id": prompt_id,
        "prompt_version_id": version_id,
        "link_state": "EXACT" if version_id else "UNRESOLVED",
        "evaluation_count": int(count or 0),
        "version_latest": _evaluation_dto(version_latest) if version_latest else None,
        "prompt_latest": _evaluation_dto(latest) if latest else None,
        "images_total": int(total or 0),
        "seen_count": int(seen or 0),
        "keep_count": int(keep or 0),
        "reject_count": int(reject or 0),
        "has_new_samples": has_new_samples,
    }


def _prompt_cursor(cursor: str) -> tuple[str, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode("utf-8")
        data = json.loads(raw)
        target = data["target"]
        offset = data["offset"]
        if not isinstance(target, str) or type(offset) is not int or offset < 0:
            raise ValueError()
        return target, offset
    except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error, json.JSONDecodeError):
        raise MobileCursorValidation("图片分页位置无效") from None


def prompt_images(
    session: Session, prompt_id: str, version_id: str | None, *,
    cursor: str | None, limit: int,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 100))
    query = _images_query(session, prompt_id, version_id)
    target = f"{prompt_id}:{version_id or ''}"
    offset = 0
    if cursor:
        stored_target, offset = _prompt_cursor(cursor)
        if stored_target != target:
            raise MobileCursorValidation("图片分页位置无效")
    total = int(session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = list(session.scalars(
        query.order_by(Image.created_at.asc(), Image.id.asc()).offset(offset).limit(limit)
    ))
    has_more = offset + len(rows) < total
    next_cursor = None
    if has_more:
        next_cursor = PROMPT_IMAGE_CURSOR_PREFIX + base64.urlsafe_b64encode(
            json.dumps({"target": target, "offset": offset + len(rows)}, separators=(",", ":")).encode("utf-8")
        ).decode("ascii").rstrip("=")
    return {
        "items": [
            {
                "image_id": row.id,
                "thumbnail_url": f"/mobile/images/{row.id}/thumbnail",
                "status": row.status,
                "is_current": False,
            }
            for row in rows
        ],
        "total": total,
        "current_index": offset,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


def evaluate_prompt(
    session: Session, *, device_id: str, prompt_id: str,
    prompt_version_id: str | None, overall_score: int,
    dimensions: dict[str, int], notes: str, client_request_id: str,
) -> dict[str, Any]:
    prompt_service.get_prompt(session, prompt_id)
    if prompt_version_id is not None:
        prompt_service.get_version(session, prompt_id, prompt_version_id)
    payload = {
        "prompt_id": prompt_id,
        "prompt_version_id": prompt_version_id,
        "overall_score": overall_score,
        "dimensions": dimensions,
        "notes": notes,
    }
    # 旧分支评分载荷不含 prompt_id / client_request_id；只用于迁移回执复核。
    legacy_payload = {
        "prompt_version_id": prompt_version_id,
        "overall_score": overall_score,
        "dimensions": dimensions,
        "notes": notes,
    }

    def apply() -> dict[str, Any]:
        request = PromptEvaluationCreateRequest(
            overall_score=overall_score,
            dimension_scores=dimensions,
            notes=notes,
            prompt_version_id=prompt_version_id,
        )
        evaluation = prompt_scoring_service.create_evaluation(
            session, prompt_id, request, source="mobile", commit=False,
        )
        result = _evaluation_dto(evaluation)
        result.pop("notes", None)
        return {**result, "client_request_id": client_request_id}

    return mobile_mutation_service.atomic_write(
        session,
        device_id=device_id,
        operation=mobile_mutation_service.OP_PROMPT_EVALUATION,
        idempotency_key=client_request_id,
        payload=payload,
        action=apply,
        legacy_payload=legacy_payload,
    )


def evaluation_receipt(session: Session, *, device_id: str, client_request_id: str) -> dict[str, Any]:
    receipt = mobile_mutation_service.find_any_receipt(
        session, device_id=device_id,
        operation=mobile_mutation_service.OP_PROMPT_EVALUATION,
        idempotency_key=client_request_id,
    )
    if receipt is None:
        return {"found": False, "evaluation": None}
    return {"found": True, "evaluation": json.loads(receipt.response_json)}
