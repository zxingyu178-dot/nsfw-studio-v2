"""system_info 表：记录系统版本信息（Phase 0 规范 §十）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class SystemInfo(Base):
    __tablename__ = "system_info"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_time: Mapped[str] = mapped_column(String(32), nullable=False, default=_now)
    updated_time: Mapped[str] = mapped_column(String(32), nullable=False, default=_now, onupdate=_now)
