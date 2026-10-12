"""Desktop loopback 管理 Bridge 的端点（Phase 0.13）。

- POST /api/v1/mobile-review/pairing/code  —— 生成 6 位配对码（只有 Desktop 能生成）；
- GET  /api/v1/mobile-review/runtime        —— Bridge 受管运行时状态；
- POST /api/v1/mobile-review/runtime/{start,stop,restart}。

安全：这些端点只在 8000（loopback）上暴露，手机无法直达。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.services import mobile_pairing_service

router = APIRouter(prefix="/mobile-review", tags=["mobile-review-admin"])


@router.post("/pairing/code", summary="生成配对码（仅 Desktop loopback）")
def create_pairing_code(session: Session = Depends(get_session)) -> dict:
    code = mobile_pairing_service.generate_pairing_code(session)
    return {"code": code, "expires_in_seconds": mobile_pairing_service.PAIRING_CODE_TTL_SECONDS}


@router.get("/devices", summary="已配对设备列表（脱敏，不含 token_hash）")
def list_devices(session: Session = Depends(get_session)) -> dict:
    return {"devices": mobile_pairing_service.list_devices(session)}


@router.post("/devices/{device_ref}/revoke", summary="吊销设备（按主键 id 或 installation_id）")
def revoke_device(device_ref: str, session: Session = Depends(get_session)) -> dict:
    return mobile_pairing_service.revoke_device(session, device_ref)


@router.get("/runtime", summary="Bridge 受管运行时状态")
async def runtime_status(request: Request) -> dict:
    svc = request.app.state.mobile_review_runtime
    return (await asyncio.to_thread(svc.status)).to_dict()


@router.post("/runtime/start", summary="启动 Bridge（幂等）")
async def runtime_start(request: Request) -> dict:
    svc = request.app.state.mobile_review_runtime
    return (await asyncio.to_thread(svc.start)).to_dict()


@router.post("/runtime/stop", summary="停止 Bridge（仅 owned）")
async def runtime_stop(request: Request) -> dict:
    svc = request.app.state.mobile_review_runtime
    return (await asyncio.to_thread(svc.stop)).to_dict()


@router.post("/runtime/restart", summary="重启 Bridge（仅 owned）")
async def runtime_restart(request: Request) -> dict:
    svc = request.app.state.mobile_review_runtime
    return (await asyncio.to_thread(svc.restart)).to_dict()
