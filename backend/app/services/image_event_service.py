"""W3.0 图片事件日志服务（Desktop 与 Mobile 共用唯一写入点）。

- 事件在业务写入的同一事务内 add + flush；是否 commit 由调用方统一控制；
- ``MobileImageEvent`` 不对 images 建外键：图片永久删除后事件仍可读；
- 游标为不透明 base64url，不直接暴露数据库 seq；
- 保留策略：v2 默认永久保留，不自动清理；只有在事件被显式裁剪后才可能返回 410。
"""
from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.ids import MOBILE_IMAGE_EVENT, new_id
from app.core.timeutil import utc_now_iso
from app.models.mobile_review import MobileImageEvent

EVENT_IMAGE_CREATED = "IMAGE_CREATED"
EVENT_IMAGE_IMPORTED = "IMAGE_IMPORTED"
EVENT_IMAGE_REVIEW_UPDATED = "IMAGE_REVIEW_UPDATED"
EVENT_IMAGE_FAVORITE_UPDATED = "IMAGE_FAVORITE_UPDATED"
EVENT_IMAGE_METADATA_UPDATED = "IMAGE_METADATA_UPDATED"
EVENT_IMAGE_REMOVED = "IMAGE_REMOVED"
EVENT_PROMPT_EVALUATED = "PROMPT_EVALUATED"
EVENT_TYPES = (
    EVENT_IMAGE_CREATED,
    EVENT_IMAGE_IMPORTED,
    EVENT_IMAGE_REVIEW_UPDATED,
    EVENT_IMAGE_FAVORITE_UPDATED,
    EVENT_IMAGE_METADATA_UPDATED,
    EVENT_IMAGE_REMOVED,
    EVENT_PROMPT_EVALUATED,
)

CURSOR_VERSION = 1
CURSOR_PREFIX = "mr2_"
DEFAULT_EVENT_LIMIT = 50
MAX_EVENT_LIMIT = 200


class CursorExpired(AppError):
    status_code = 410
    code = "CURSOR_EXPIRED"
    message = "同步游标已过期，请先获取 snapshot"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message, details={"snapshot_required": True})


def latest_event_seq(session: Session, image_id: str) -> int:
    """图片当前 revision：该图最新事件 seq（十进制字符串，单调递增）。"""
    value = session.execute(
        select(func.max(MobileImageEvent.seq)).where(MobileImageEvent.image_id == image_id)
    ).scalar_one_or_none()
    return int(value or 0)


def latest_event_seqs(session: Session, image_ids: list[str]) -> dict[str, int]:
    """批量读取图片最新 seq，避免详情/快照 N+1 查询。"""
    if not image_ids:
        return {}
    rows = session.execute(
        select(MobileImageEvent.image_id, func.max(MobileImageEvent.seq))
        .where(MobileImageEvent.image_id.in_(image_ids))
        .group_by(MobileImageEvent.image_id)
    ).all()
    return {str(image_id): int(seq) for image_id, seq in rows if image_id}


def image_revision(session: Session, image) -> str:
    """兼容旧调用名：revision 必须是事件 seq，不能再用毫秒时间戳。"""
    return str(latest_event_seq(session, image.id))


def image_payload(image) -> dict[str, Any]:
    """只含手机端可见字段；绝不写 file_path / DataRoot 绝对路径。"""
    return {
        "image_id": image.id,
        "width": image.width,
        "height": image.height,
        "status": image.status,
        "is_favorite": bool(image.favorite),
        "kind": image.kind,
        "source": image.source,
        "job_id": image.job_id,
        "seed": image.seed,
        "created_at": image.created_at,
        "updated_at": image.updated_at,
    }


def record_event(
    session: Session,
    event_type: str,
    *,
    image_id: str | None = None,
    revision: str | None = None,
    payload: dict[str, Any] | None = None,
    commit: bool = False,
) -> MobileImageEvent:
    """写入事件并 flush 以获得单调 seq；默认不 commit（由外层事务统一提交）。"""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"非法移动端事件类型: {event_type}")
    event = MobileImageEvent(
        event_id=new_id(MOBILE_IMAGE_EVENT),
        event_type=event_type,
        image_id=image_id,
        revision=revision,
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
        created_at=utc_now_iso(),
    )
    session.add(event)
    session.flush()
    if event.image_id is not None and event.revision is None:
        # 事件自身的 seq 就是图片 revision；flush 后才有单调序号。
        event.revision = str(event.seq)
    if commit:
        session.commit()
    return event


def record_images_created(session: Session, images: list, *, source: str) -> None:
    event_type = EVENT_IMAGE_IMPORTED if source == "import" else EVENT_IMAGE_CREATED
    for image in images:
        record_event(
            session, event_type,
            image_id=image.id, payload=image_payload(image),
        )


def record_review_change(
    session: Session,
    image,
    *,
    review_changed: bool,
    favorite_changed: bool,
    metadata_changed: bool = False,
    note: str | None = None,
) -> None:
    """审核 / 收藏 / 元数据事件（同一事务；调用方负责 commit/rollback）。"""
    if review_changed:
        payload = image_payload(image)
        payload["review_note"] = note if note is not None else (image.review_note or "")
        record_event(
            session, EVENT_IMAGE_REVIEW_UPDATED,
            image_id=image.id, payload=payload,
        )
    if favorite_changed:
        record_event(
            session, EVENT_IMAGE_FAVORITE_UPDATED,
            image_id=image.id, payload=image_payload(image),
        )
    if metadata_changed:
        payload = image_payload(image)
        payload["review_note"] = note if note is not None else (image.review_note or "")
        record_event(
            session, EVENT_IMAGE_METADATA_UPDATED,
            image_id=image.id, payload=payload,
        )


def record_image_removed(session: Session, image) -> None:
    """必须在 DELETE images 之前、同一事务内调用；事件无 images 外键。"""
    record_event(
        session, EVENT_IMAGE_REMOVED,
        image_id=image.id, payload=image_payload(image),
    )


def record_prompt_evaluated(session: Session, evaluation) -> None:
    record_event(
        session, EVENT_PROMPT_EVALUATED,
        image_id=None,
        revision=evaluation.prompt_version_id or evaluation.prompt_id,
        payload={
            "evaluation_id": evaluation.id,
            "prompt_id": evaluation.prompt_id,
            "prompt_version_id": evaluation.prompt_version_id,
            "overall_score": evaluation.overall_score,
            "source": evaluation.source,
            "created_at": evaluation.created_at,
        },
    )


# ===== 不透明游标 =====


def encode_cursor(seq: int) -> str:
    raw = json.dumps({"v": CURSOR_VERSION, "seq": int(seq)}, separators=(",", ":")).encode("utf-8")
    return CURSOR_PREFIX + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> int:
    if not cursor.startswith(CURSOR_PREFIX):
        raise CursorExpired()
    encoded = cursor[len(CURSOR_PREFIX):]
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        if not isinstance(data, dict) or data.get("v") != CURSOR_VERSION:
            raise CursorExpired()
        seq = int(data["seq"])
        if seq < 0:
            raise CursorExpired()
        return seq
    except (ValueError, TypeError, KeyError, binascii.Error, json.JSONDecodeError):
        raise CursorExpired() from None


def newest_seq(session: Session) -> int:
    value = session.execute(select(func.max(MobileImageEvent.seq))).scalar_one_or_none()
    return int(value or 0)


def oldest_seq(session: Session) -> int | None:
    value = session.execute(select(func.min(MobileImageEvent.seq))).scalar_one_or_none()
    return int(value) if value is not None else None


def resolve_cursor(session: Session, cursor: str | None) -> int:
    """解析并校验游标；过期/非法/未来游标统一 410 CURSOR_EXPIRED。"""
    if cursor is None or cursor == "":
        return 0
    cursor_seq = decode_cursor(cursor)
    oldest = oldest_seq(session)
    if oldest is not None and cursor_seq < oldest - 1:
        raise CursorExpired()
    if cursor_seq > newest_seq(session):
        raise CursorExpired()
    return cursor_seq


def list_events(
    session: Session, *, cursor: str | None, limit: int = DEFAULT_EVENT_LIMIT,
) -> dict[str, Any]:
    """按 seq 升序返回增量事件；不漏、不重、支持断点恢复。"""
    limit = max(1, min(int(limit), MAX_EVENT_LIMIT))
    cursor_seq = resolve_cursor(session, cursor)

    rows = list(session.scalars(
        select(MobileImageEvent)
        .where(MobileImageEvent.seq > cursor_seq)
        .order_by(MobileImageEvent.seq.asc())
        .limit(limit + 1)
    ))
    has_more = len(rows) > limit
    rows = rows[:limit]
    last_seq = rows[-1].seq if rows else cursor_seq
    return {
        "events": [
            {
                "event_id": row.event_id,
                "event_type": row.event_type,
                "image_id": row.image_id,
                "revision": row.revision,
                "payload": json.loads(row.payload_json or "{}"),
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "next_cursor": encode_cursor(last_seq),
        "has_more": has_more,
        "server_time": utc_now_iso(),
    }
