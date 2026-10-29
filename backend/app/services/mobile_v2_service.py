"""审核桥v2：有序持久增量，不读取或推断当前提示词正文。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Image, Job, Prompt, PromptVersion
from app.services.image_review_session_service import _image_summary
from app.core.errors import ConflictError, NotFoundError, UnauthorizedError
from app.core.timeutil import utc_now_iso
from app.models.mobile_review import MobileReviewDevice


class CursorExpired(AppError):
    status_code = 410
    code = "CURSOR_EXPIRED"
    message = "同步位置已失效，请重新同步"


def _cursor(session: Session, seq: int) -> str:
    epoch = session.execute(text("SELECT epoch FROM mobile_feed_identity WHERE id=1")).scalar_one()
    payload = str(seq)
    signature = hmac.new(epoch.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}.{signature}".encode()).decode().rstrip("=")


def _position(session: Session, cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        value, _signature = raw.split(".")
        seq = int(value)
        if seq < 0 or not hmac.compare_digest(_cursor(session, seq), cursor):
            raise ValueError()
        maximum = session.execute(text("SELECT coalesce(max(seq),0) FROM mobile_image_events")).scalar_one()
        if seq > maximum:
            raise ValueError()
        return seq
    except (ValueError, UnicodeError):
        raise CursorExpired() from None


def _json(raw: str) -> dict:
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def image_details(session: Session, image: Image) -> dict:
    job = session.get(Job, image.job_id) if image.job_id else None
    snapshot = _json(job.workbench_snapshot_json) if job else {}
    prompt_id = snapshot.get("source_prompt_id")
    version_id = snapshot.get("source_prompt_version_id")
    # 仅可信生成Job快照的显式身份，绝不按文本相同认领，版本未知不绑定最新版。
    if not isinstance(prompt_id, str) or session.get(Prompt, prompt_id) is None:
        prompt_id, version_id = None, None
    version = session.get(PromptVersion, version_id) if isinstance(version_id, str) else None
    if version is None or version.prompt_id != prompt_id:
        version_id = None
    revision = session.execute(text(
        "SELECT coalesce(max(seq),0) FROM mobile_image_events WHERE image_id=:id"
    ), {"id": image.id}).scalar_one()
    metadata = _json(image.metadata_json)
    return {
        "image_id": image.id, "created_at": image.created_at,
        "generated_at": metadata.get("generated_at"),
        "width": image.width, "height": image.height,
        "positive_prompt": job.positive_prompt_snapshot if job else None,
        "negative_prompt": job.negative_prompt_snapshot if job else None,
        "prompt_id": prompt_id, "prompt_version_id": version_id,
        "link_state": "EXACT" if version_id else "UNRESOLVED" if prompt_id else "UNLINKED",
        "job_id": image.job_id, "module_id": job.module_id if job else None,
        "seed": image.seed, "model": None, "size_bytes": None, "mime": None,
        "updated_at": image.updated_at, "revision": str(revision),
    }


def feed(session: Session, cursor: str | None, limit: int) -> dict:
    position = _position(session, cursor)
    events = session.execute(text(
        "SELECT seq,image_id,event FROM mobile_image_events WHERE seq>:seq ORDER BY seq LIMIT :limit"
    ), {"seq": position, "limit": limit + 1}).mappings().all()
    selected = events[:limit]
    items = []
    for event in selected:
        image = session.get(Image, event["image_id"])
        if image is None:
            item = {"image_id": event["image_id"], "event": "REMOVE", "revision": str(event["seq"])}
        else:
            details = image_details(session, image)
            item = {**_image_summary(image), "event": "UPSERT", "revision": details["revision"],
                "prompt": {key: details[key] for key in ("prompt_id", "prompt_version_id", "link_state")}}
        items.append(item)
    next_position = selected[-1]["seq"] if selected else position
    return {"items": items, "next_cursor": _cursor(session, next_position),
        "has_more": len(events) > limit, "resumed": cursor is not None}


def atomic_write(session: Session, device_id: str, request_id: str, operation: str, payload: dict, action) -> dict:
    """SQLite先取得写权再读回执；业务事实和回执必须同一事务耐久化。"""
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    session.rollback()
    session.execute(text("BEGIN IMMEDIATE"))
    try:
        device = session.get(MobileReviewDevice, device_id)
        if device is None or device.revoked:
            raise UnauthorizedError()
        old = session.execute(text(
            "SELECT operation,fingerprint,result_json FROM mobile_write_receipts WHERE device_id=:device AND request_id=:request"
        ), {"device": device_id, "request": request_id}).mappings().first()
        if old:
            if old["operation"] != operation or old["fingerprint"] != fingerprint:
                raise ConflictError("同一请求号的内容发生变化", code="IDEMPOTENCY_CONFLICT")
            session.rollback()
            return json.loads(old["result_json"])
        result = action()
        session.execute(text(
            "INSERT INTO mobile_write_receipts(device_id,request_id,operation,fingerprint,result_json) "
            "VALUES (:device,:request,:operation,:fingerprint,:result)"
        ), {"device": device_id, "request": request_id, "operation": operation,
            "fingerprint": fingerprint, "result": json.dumps(result, ensure_ascii=False)})
        session.commit()
        return result
    except BaseException:
        session.rollback()
        raise


def decide(session: Session, device_id: str, image_id: str, payload: dict) -> dict:
    def apply():
        image = session.get(Image, image_id)
        if image is None:
            raise NotFoundError("图片不存在", code="IMAGE_NOT_FOUND")
        if image.updated_at != payload["expected_updated_at"]:
            raise ConflictError("图片已更新，请核对最新状态", code="REVIEW_CONFLICT", details={"image": _image_summary(image)})
        now = utc_now_iso()
        if now <= image.updated_at:
            from datetime import datetime, timedelta
            now = (datetime.fromisoformat(image.updated_at.replace("Z", "+00:00")) + timedelta(milliseconds=1)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        action = payload.get("action")
        if action is not None:
            image.status = {"KEEP": "KEEP", "REJECT": "REJECT", "RESET": "NEW"}[action]
            image.review_status = {"KEEP": "KEPT", "REJECT": "REJECTED", "RESET": "UNREVIEWED"}[action]
            image.reviewed_at = None if action == "RESET" else now
        if payload.get("favorite") is not None:
            image.favorite = payload["favorite"]
        image.updated_at = now
        session.flush()
        session.execute(text(
            "INSERT INTO mobile_image_seen(device_id,image_id,seen) VALUES (:device,:image,:seen) "
            "ON CONFLICT(device_id,image_id) DO UPDATE SET seen=excluded.seen"
        ), {"device": device_id, "image": image_id,
            "seen": int(action != "RESET" or payload.get("favorite") is not None)})
        revision = image_details(session, image)["revision"]
        return {"image_id": image.id, "status": image.status, "is_favorite": image.favorite,
            "updated_at": image.updated_at, "revision": revision}
    return atomic_write(session, device_id, payload["client_request_id"], "decision:" + image_id, payload, apply)
