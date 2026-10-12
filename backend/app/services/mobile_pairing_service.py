"""Mobile Review 配对与设备鉴权服务（Phase 0.13）。

安全红线：
- **device 只存 token SHA-256**（``token_hash``），绝不存 Bearer 明文；
- 配对码 6 位数字、一次性、10 分钟过期、成功即失效，**只存 hash**；
- 配对码只能由 Desktop loopback（8000）``POST /api/v1/mobile-review/pairing/code`` 生成；
- Bridge（8767）开放端点只有 health / pairing status / pairing verify，其余全部 Bearer。
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError, ValidationError
from app.core.ids import MOBILE_DEVICE, MOBILE_PAIRING_CODE, new_id
from app.core.timeutil import utc_now_iso
from app.models.mobile_review import MobileReviewDevice, MobileReviewPairingCode

PAIRING_CODE_TTL_SECONDS = 600  # 10 分钟
PAIRING_CODE_DIGITS = 6
TOKEN_BYTES = 32  # 256-bit token → hex


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_token() -> str:
    """生成随机 Bearer token（返回给手机一次；此后只其 hash 入库）。"""
    return secrets.token_hex(TOKEN_BYTES)


class PairingCodeInvalid(AppError):
    status_code = 400
    code = "PAIRING_CODE_INVALID"
    message = "配对码无效或已过期"


class MobileUnauthorized(AppError):
    status_code = 401
    code = "UNAUTHORIZED"
    message = "缺少或无效的 Bearer token"


class DeviceRevoked(AppError):
    status_code = 401
    code = "DEVICE_REVOKED"
    message = "设备已被吊销"


@dataclass(frozen=True)
class PairedDevice:
    device_id: str
    installation_id: str
    name: str
    token: str  # 仅 verify 成功时返回一次；其余场景不得返回
    paired_at: str


def generate_pairing_code(session: Session) -> str:
    """Desktop loopback 生成一个 6 位配对码（明文只返回这一次，DB 只存 hash）。"""
    code = f"{secrets.randbelow(10 ** PAIRING_CODE_DIGITS):0{PAIRING_CODE_DIGITS}d}"
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=PAIRING_CODE_TTL_SECONDS))
    row = MobileReviewPairingCode(
        id=new_id(MOBILE_PAIRING_CODE),
        code_hash=_sha256_hex(code),
        expires_at=expires_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        used=False,
    )
    session.add(row)
    session.commit()
    return code


def pairing_status(session: Session) -> dict:
    """开放端点：当前是否存在有效（未用、未过期）配对码。不下发码本身。"""
    now = utc_now_iso()
    valid = session.execute(
        select(MobileReviewPairingCode).where(
            MobileReviewPairingCode.used.is_(False),
            MobileReviewPairingCode.expires_at > now,
        )
    ).scalars().first()
    return {"pairing_available": valid is not None}


def verify_pairing(session: Session, installation_id: str, device_name: str, code: str) -> PairedDevice:
    """开放端点：用配对码换 Bearer token。成功即把配对码标记为已用。"""
    installation_id = (installation_id or "").strip()
    code = (code or "").strip()
    if not installation_id:
        raise ValidationError("缺少 installation_id", code="INSTALLATION_ID_REQUIRED")
    if not (len(code) == PAIRING_CODE_DIGITS and code.isdigit()):
        raise PairingCodeInvalid()

    now = utc_now_iso()
    code_hash = _sha256_hex(code)
    record = session.execute(
        select(MobileReviewPairingCode).where(MobileReviewPairingCode.code_hash == code_hash)
    ).scalars().first()

    if record is None or record.used or record.expires_at <= now:
        raise PairingCodeInvalid()

    # 一次性：成功即失效（同事务内提交，杜绝并发复用）
    record.used = True

    token = generate_token()
    token_hash = _sha256_hex(token)
    device = session.execute(
        select(MobileReviewDevice).where(MobileReviewDevice.installation_id == installation_id)
    ).scalars().first()
    if device is None:
        device = MobileReviewDevice(
            id=new_id(MOBILE_DEVICE),
            installation_id=installation_id,
            name=device_name or "",
            token_hash=token_hash,
        )
        session.add(device)
    else:
        device.name = device_name or device.name
        device.token_hash = token_hash
        device.revoked = False
        device.paired_at = utc_now_iso()
    device.last_seen_at = now
    session.commit()
    session.refresh(device)
    return PairedDevice(
        device_id=device.id,
        installation_id=device.installation_id,
        name=device.name,
        token=token,
        paired_at=device.paired_at,
    )


def authenticate_token(session: Session, token: str) -> MobileReviewDevice:
    """Bearer 鉴权：按 token hash 查未吊销设备，命中则刷新 last_seen_at。"""
    token = (token or "").strip()
    if not token:
        raise MobileUnauthorized()
    device = session.execute(
        select(MobileReviewDevice).where(
            MobileReviewDevice.token_hash == _sha256_hex(token),
            MobileReviewDevice.revoked.is_(False),
        )
    ).scalars().first()
    if device is None:
        # 区分"已吊销"还是"根本无此设备"：查一次是否存在但 revoked
        revoked = session.execute(
            select(MobileReviewDevice).where(
                MobileReviewDevice.token_hash == _sha256_hex(token),
                MobileReviewDevice.revoked.is_(True),
            )
        ).scalars().first()
        if revoked is not None:
            raise DeviceRevoked()
        raise MobileUnauthorized()
    device.last_seen_at = utc_now_iso()
    session.commit()
    return device


# ---- Desktop loopback 设备管理（绝不下发 token_hash / token） ----


def list_devices(session: Session) -> list[dict]:
    """返回全部已配对设备（脱敏：不含 token_hash / token）。"""
    rows = session.execute(
        select(MobileReviewDevice).order_by(MobileReviewDevice.paired_at.desc())
    ).scalars().all()
    return [
        {
            "id": d.id,
            "installation_id": d.installation_id,
            "name": d.name,
            "paired_at": d.paired_at,
            "last_seen_at": d.last_seen_at,
            "revoked": bool(d.revoked),
        }
        for d in rows
    ]


class DeviceNotFound(NotFoundError):
    status_code = 404
    code = "DEVICE_NOT_FOUND"
    message = "设备不存在"


def revoke_device(session: Session, device_ref: str) -> dict:
    """按主键 id 或 installation_id 吊销设备（token 立即 401 DEVICE_REVOKED）。"""
    device = session.get(MobileReviewDevice, device_ref)
    if device is None:
        device = session.execute(
            select(MobileReviewDevice).where(
                MobileReviewDevice.installation_id == device_ref
            )
        ).scalars().first()
    if device is None:
        raise DeviceNotFound()
    device.revoked = True
    session.commit()
    return {
        "id": device.id,
        "installation_id": device.installation_id,
        "revoked": True,
    }
