"""Mobile Bridge 专用依赖：请求级 DB 会话 + Bearer 设备鉴权。

与 Desktop deps 同源（同一个 session_factory / StorageManager），但鉴权走 Bearer。
开放端点（health / pairing status / pairing verify）不注入当前设备。
"""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.models.mobile_review import MobileReviewDevice
from app.services import mobile_pairing_service
from app.storage.manager import StorageManager


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_storage(request: Request) -> StorageManager:
    return request.app.state.storage


def get_current_device(
    request: Request,
    session: Session = Depends(get_session),
) -> MobileReviewDevice:
    """Bearer 鉴权：除开放端点外全部注入；失败由 AppError → 401 envelope。"""
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer":
        raise mobile_pairing_service.MobileUnauthorized()
    return mobile_pairing_service.authenticate_token(session, token)
