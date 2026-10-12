"""Mobile Bridge 审核会话端点（Bearer）。

冻结式队列 + 单事务 decision + 409 REVIEW_CONFLICT。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.mobile.deps import get_current_device, get_session
from app.models.mobile_review import MobileReviewDevice
from app.services import image_review_session_service as svc

router = APIRouter(prefix="/mobile/review", tags=["mobile-review"])


class CreateSessionRequest(BaseModel):
    filter: dict[str, Any] | None = None


class DecisionRequest(BaseModel):
    item_index: int | None = None
    image_id: str | None = None
    action: str | None = None
    favorite: bool | None = None
    expected_status: str | None = None
    expected_updated_at: str | None = None


class PositionRequest(BaseModel):
    item_index: int = Field(ge=0)


@router.post("/sessions", summary="创建冻结审核会话（Bearer）", status_code=201)
def create_session(body: CreateSessionRequest,
                   session: Session = Depends(get_session),
                   _device: MobileReviewDevice = Depends(get_current_device)) -> dict:
    return svc.create_session(session, body.filter).to_dict()


@router.get("/sessions/latest", summary="恢复最近会话（不重建；无则 404）")
def latest_session(session: Session = Depends(get_session),
                   _device: MobileReviewDevice = Depends(get_current_device)) -> dict:
    latest = svc.get_latest_session(session)
    if latest is None:
        from app.services.image_review_session_service import ReviewSessionNotFound
        raise ReviewSessionNotFound()
    return latest.to_dict()


@router.get("/sessions/{session_id}/queue", summary="分页取冻结队列（绝对 index 不压缩）")
def queue(session_id: str,
          page: int = Query(default=1, ge=1),
          page_size: int = Query(default=50, ge=1, le=200),
          db: Session = Depends(get_session),
          _device: MobileReviewDevice = Depends(get_current_device)) -> dict:
    return svc.queue_page(db, session_id, page=page, page_size=page_size)


@router.post("/sessions/{session_id}/decision", summary="一次 decision（同事务）")
def decision(session_id: str, body: DecisionRequest,
             db: Session = Depends(get_session),
             _device: MobileReviewDevice = Depends(get_current_device)) -> dict:
    return svc.apply_decision(
        db, session_id,
        item_index=body.item_index, image_id=body.image_id,
        action=body.action, favorite=body.favorite,
        expected_status=body.expected_status, expected_updated_at=body.expected_updated_at,
    )


@router.post("/sessions/{session_id}/position", summary="记录浏览位置（断点续看）")
def position(session_id: str, body: PositionRequest,
             db: Session = Depends(get_session),
             _device: MobileReviewDevice = Depends(get_current_device)) -> dict:
    return svc.update_position(db, session_id, body.item_index).to_dict()


@router.post("/sessions/{session_id}/complete", summary="标记完成（仍有未审则不强完成）")
def complete(session_id: str,
             db: Session = Depends(get_session),
             _device: MobileReviewDevice = Depends(get_current_device)) -> dict:
    return svc.complete_session(db, session_id)
