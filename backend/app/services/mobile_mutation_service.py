"""W3.0 移动端幂等回执（device + operation + idempotency_key 唯一）。"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.core.ids import MOBILE_MUTATION_RECEIPT, new_id
from app.models.mobile_review import MobileMutationReceipt


def payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def find_receipt(
    session: Session, *, device_id: str, operation: str, idempotency_key: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """命中相同 key：payload 一致 → 返回原始响应；不一致 → 409 IDEMPOTENCY_CONFLICT。"""
    receipt = session.execute(
        select(MobileMutationReceipt).where(
            MobileMutationReceipt.device_id == device_id,
            MobileMutationReceipt.operation == operation,
            MobileMutationReceipt.idempotency_key == idempotency_key,
        )
    ).scalars().first()
    if receipt is None:
        return None
    if receipt.payload_hash != payload_hash(payload):
        raise ConflictError(
            "idempotency_key 已用于不同的请求内容",
            code="IDEMPOTENCY_CONFLICT",
        )
    return json.loads(receipt.response_json)


def add_receipt(
    session: Session, *, device_id: str, operation: str, idempotency_key: str,
    payload: dict[str, Any], response: dict[str, Any],
) -> None:
    """只 add，不 commit；调用方与业务状态/事件在同一事务提交。"""
    session.add(MobileMutationReceipt(
        id=new_id(MOBILE_MUTATION_RECEIPT),
        device_id=device_id,
        operation=operation,
        idempotency_key=idempotency_key,
        payload_hash=payload_hash(payload),
        response_json=json.dumps(response, ensure_ascii=False),
    ))


def replay_or_none(
    session: Session, *, device_id: str, operation: str, idempotency_key: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """并发兜底：IntegrityError 后回滚，再查同 key 回执。

    返回 None 表示确实是其它错误，调用方应重新抛出。
    """
    session.rollback()
    return find_receipt(
        session, device_id=device_id, operation=operation,
        idempotency_key=idempotency_key, payload=payload,
    )


__all__ = ["payload_hash", "find_receipt", "add_receipt", "replay_or_none"]
