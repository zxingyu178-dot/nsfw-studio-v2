"""移动端写事务与幂等回执（W3.0 起步，W3.1 原子化）。

- 回执唯一键 ``(device_id, operation, idempotency_key)``；
- ``operation`` 使用稳定短标识（image_decision / prompt_evaluation / image_review），
  不把长 UUID 拼进字段；目标身份放在 payload 哈希里；
- SQLite 先 ``BEGIN IMMEDIATE`` 取得写锁，再检查设备有效性与回执，
  最后业务变更 + 事件 + 回执同一事务提交；
- 旧分支回执在 0022 合并时保留原始指纹（``legacy_fp:`` 前缀），重放时按旧算法复核。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, UnauthorizedError
from app.core.ids import MOBILE_MUTATION_RECEIPT, new_id
from app.models.mobile_review import MobileMutationReceipt, MobileReviewDevice

OP_IMAGE_DECISION = "image_decision"
OP_IMAGE_REVIEW = "image_review"
OP_PROMPT_EVALUATION = "prompt_evaluation"

LEGACY_HASH_PREFIX = "legacy_fp:"


def payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _legacy_payload_hash(payload: dict[str, Any]) -> str:
    """参考分支的旧指纹算法（json.dumps 默认分隔符），只用于迁移回执重放。"""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _receipt_query(session: Session, device_id: str, operation: str, key: str):
    return session.execute(
        select(MobileMutationReceipt).where(
            MobileMutationReceipt.device_id == device_id,
            MobileMutationReceipt.operation == operation,
            MobileMutationReceipt.idempotency_key == key,
        )
    ).scalars().first()


def _match_or_conflict(
    receipt: MobileMutationReceipt,
    payload: dict[str, Any],
    legacy_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    stored = receipt.payload_hash
    if stored.startswith(LEGACY_HASH_PREFIX):
        fingerprint = stored[len(LEGACY_HASH_PREFIX):]
        if legacy_payload is not None and _legacy_payload_hash(legacy_payload) == fingerprint:
            return json.loads(receipt.response_json)
        raise ConflictError(
            "client_request_id 已用于不同的请求内容",
            code="IDEMPOTENCY_CONFLICT",
        )
    if stored != payload_hash(payload):
        raise ConflictError(
            "client_request_id 已用于不同的请求内容",
            code="IDEMPOTENCY_CONFLICT",
        )
    return json.loads(receipt.response_json)


def find_receipt(
    session: Session, *, device_id: str, operation: str, idempotency_key: str,
    payload: dict[str, Any], legacy_payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """命中相同 key：载荷一致 → 返回原始响应；不一致 → 409 IDEMPOTENCY_CONFLICT。"""
    receipt = _receipt_query(session, device_id, operation, idempotency_key)
    if receipt is None:
        return None
    return _match_or_conflict(receipt, payload, legacy_payload)


def find_any_receipt(
    session: Session, *, device_id: str, operation: str, idempotency_key: str,
) -> MobileMutationReceipt | None:
    """按设备+操作+请求号读取回执（跨设备天然隔离；不校验载荷）。"""
    return _receipt_query(session, device_id, operation, idempotency_key)


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
    payload: dict[str, Any], legacy_payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """并发兜底：IntegrityError 后回滚，再查同 key 回执。"""
    session.rollback()
    return find_receipt(
        session, device_id=device_id, operation=operation,
        idempotency_key=idempotency_key, payload=payload, legacy_payload=legacy_payload,
    )


def atomic_write(
    session: Session,
    *,
    device_id: str,
    operation: str,
    idempotency_key: str,
    payload: dict[str, Any],
    action: Callable[[], dict[str, Any]],
    legacy_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """SQLite 写锁串行化 + 设备复核 + 业务/事件/回执同一事务。"""
    session.rollback()
    session.execute(text("BEGIN IMMEDIATE"))
    try:
        device = session.get(MobileReviewDevice, device_id)
        if device is None or bool(device.revoked):
            raise UnauthorizedError("设备已被吊销", code="DEVICE_REVOKED")

        replay = find_receipt(
            session, device_id=device_id, operation=operation,
            idempotency_key=idempotency_key, payload=payload,
            legacy_payload=legacy_payload,
        )
        if replay is not None:
            session.rollback()
            return replay

        result = action()
        add_receipt(
            session, device_id=device_id, operation=operation,
            idempotency_key=idempotency_key, payload=payload, response=result,
        )
        session.commit()
        return result
    except BaseException:
        session.rollback()
        raise


__all__ = [
    "OP_IMAGE_DECISION", "OP_IMAGE_REVIEW", "OP_PROMPT_EVALUATION",
    "payload_hash", "find_receipt", "add_receipt", "replay_or_none", "atomic_write",
]
