"""Desktop 审核会话命名空间（Phase 0.13 桥接）。

``/api/v1/review/*`` —— 供桌面前端后续迁移，替代前端对 ``status=NEW`` 的动态 offset 翻页。
**与手机共用同一个 ImageReviewSessionService**（冻结队列语义一致）；桌面走 loopback，
无 Bearer、无 mobile envelope（保持 Desktop 响应格式不变）。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.services import image_review_session_service as svc
from app.services.image_review_session_service import ReviewSessionNotFound

router = APIRouter(prefix="/review", tags=["review"])


class CreateSessionRequest(BaseModel):
    filter: dict[str, Any] | None = None
    # v0.37：all=全部未审核（默认，旧语义）；only_new=仅新到（排除旧会话成员）
    mode: str = "all"
    exclude_session_id: str | None = None
    # 显式换批：把旧 ACTIVE 会话标为 ABANDONED（保留 items）
    close_active: bool = False


class DecisionRequest(BaseModel):
    item_index: int | None = None
    image_id: str | None = None
    action: str | None = None
    favorite: bool | None = None
    expected_status: str | None = None
    expected_updated_at: str | None = None


class PositionRequest(BaseModel):
    item_index: int = Field(ge=0)


@router.post("/sessions", summary="创建冻结审核会话", status_code=201)
def create_session(body: CreateSessionRequest,
                   session: Session = Depends(get_session)) -> dict:
    return svc.create_session(
        session, body.filter, mode=body.mode,
        exclude_session_id=body.exclude_session_id, close_active=body.close_active,
    ).to_dict()


@router.get("/sessions/latest", summary="恢复最近会话（不重建）")
def latest_session(session: Session = Depends(get_session)) -> dict:
    latest = svc.get_latest_session(session)
    if latest is None:
        raise ReviewSessionNotFound()
    return latest.to_dict()


@router.get("/sessions/{session_id}/queue", summary="分页取冻结队列")
def queue(session_id: str,
          page: int = Query(default=1, ge=1),
          page_size: int = Query(default=50, ge=1, le=200),
          session: Session = Depends(get_session)) -> dict:
    return svc.queue_page(session, session_id, page=page, page_size=page_size)


@router.post("/sessions/{session_id}/decision", summary="一次 decision（同事务）")
def decision(session_id: str, body: DecisionRequest,
             session: Session = Depends(get_session)) -> dict:
    return svc.apply_decision(
        session, session_id,
        item_index=body.item_index, image_id=body.image_id,
        action=body.action, favorite=body.favorite,
        expected_status=body.expected_status, expected_updated_at=body.expected_updated_at,
    )


@router.post("/sessions/{session_id}/position", summary="记录浏览位置")
def position(session_id: str, body: PositionRequest,
             session: Session = Depends(get_session)) -> dict:
    return svc.update_position(session, session_id, body.item_index).to_dict()


@router.post("/sessions/{session_id}/complete", summary="标记完成（仍有未审则不强完成）")
def complete(session_id: str, session: Session = Depends(get_session)) -> dict:
    return svc.complete_session(session, session_id)


@router.post("/sessions/{session_id}/abandon", summary="显式放弃会话（保留 items，不删除）")
def abandon(session_id: str, session: Session = Depends(get_session)) -> dict:
    return svc.abandon_session(session, session_id)


@router.get("/sessions/{session_id}/new-count", summary="会话之外的新待审图片数量")
def new_count(session_id: str, session: Session = Depends(get_session)) -> dict:
    return svc.count_new_since_session(session, session_id)
