"""Mobile Review Bridge 生图进度。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.mobile.deps import get_current_device, get_session
from app.models.mobile_review import MobileReviewDevice
from app.services import mobile_generation_service

router = APIRouter(prefix="/mobile/generation", tags=["mobile-generation"])


@router.get("/progress", summary="当前生图进度（已配对设备）")
def generation_progress(
    response: Response,
    session: Session = Depends(get_session),
    _device: MobileReviewDevice = Depends(get_current_device),
) -> dict[str, int | None]:
    response.headers["Cache-Control"] = "no-store"
    return mobile_generation_service.read_progress(session)
