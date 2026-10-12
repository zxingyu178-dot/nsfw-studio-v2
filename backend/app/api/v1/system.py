"""System Status API（Phase 0.12 Task7）：只读系统/存储/引擎运行时摘要。

    GET /api/v1/system/status

Settings 页升级为"系统与维护中心"的数据来源；只读，绝不返回敏感配置内容。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.system import SystemStatusResponse
from app.services import system_service

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse,
            summary="只读系统状态摘要（版本/路径/磁盘/图片计数/最新迁移/引擎运行时）")
def system_status(request: Request, session: Session = Depends(get_session)) -> SystemStatusResponse:
    engine_runtime = getattr(request.app.state, "engine_runtime", None)
    summary = system_service.collect_system_status(
        session, request.app.state.settings, engine_runtime
    )
    return SystemStatusResponse(**summary)
