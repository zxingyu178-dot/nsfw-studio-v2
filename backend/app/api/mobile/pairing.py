"""Mobile Bridge 配对端点（开放，无需 Bearer）。

- GET  /mobile/pairing/status  —— 是否存在有效配对码（不下发码）；
- POST /mobile/pairing/verify  —— 用 6 位配对码换 Bearer token（一次性）。

配对码本身只能由 Desktop loopback POST /api/v1/mobile-review/pairing/code 生成。
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.mobile.deps import get_session
from app.services import mobile_pairing_service

router = APIRouter(prefix="/mobile/pairing", tags=["mobile-pairing"])


class PairingVerifyRequest(BaseModel):
    installation_id: str = Field(min_length=1, max_length=128)
    device_name: str = Field(default="", max_length=128)
    code: str = Field(min_length=6, max_length=6)


@router.get("/status", summary="配对是否可用（开放）")
def pairing_status(session: Session = Depends(get_session)) -> dict:
    return mobile_pairing_service.pairing_status(session)


@router.post("/verify", summary="配对码换 Bearer token（开放，一次性）")
def pairing_verify(body: PairingVerifyRequest,
                   session: Session = Depends(get_session)) -> dict:
    paired = mobile_pairing_service.verify_pairing(
        session,
        installation_id=body.installation_id,
        device_name=body.device_name,
        code=body.code,
    )
    return {
        "device_id": paired.device_id,
        "installation_id": paired.installation_id,
        "name": paired.name,
        "token": paired.token,
        "paired_at": paired.paired_at,
    }
