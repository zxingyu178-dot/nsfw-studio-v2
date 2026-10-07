"""API 依赖：数据库会话与存储管理器。"""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.storage.manager import StorageManager


def get_session(request: Request) -> Iterator[Session]:
    """请求级 SQLAlchemy 会话（由 lifespan 创建的 session_factory 提供）。"""
    factory = request.app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_storage(request: Request) -> StorageManager:
    return request.app.state.storage
