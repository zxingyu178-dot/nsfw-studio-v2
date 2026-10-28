"""Mobile Review Bridge 模型（Phase 0.13）。

- ``MobileReviewDevice``：已配对手机。**只存 token SHA-256（token_hash）**，
  绝不存 Bearer 明文；installation_id 唯一（同一台手机重装/换 token 走 upsert）。
- ``MobileReviewPairingCode``：Desktop loopback 生成的 6 位配对码，只存 hash，
  一次性、10 分钟过期、成功即失效。
- ``ImageReviewSession``：冻结式审核会话——创建时把符合 filter 的 image_id 顺序冻结，
  后续 NEW→KEEP/REJECT 不改变队列。
- ``ImageReviewSessionItem``：会话内一条队列项（绝对 item_index，不压缩）。
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import utc_now_iso
from app.database.base import Base


class MobileReviewDevice(Base):
    __tablename__ = "mobile_review_devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    installation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    paired_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)
    last_seen_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    revoked: Mapped[bool] = mapped_column(nullable=False, default=False)


class MobileReviewPairingCode(Base):
    __tablename__ = "mobile_review_pairing_codes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[str] = mapped_column(String(32), nullable=False)
    used: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)


class ImageReviewSession(Base):
    __tablename__ = "mobile_review_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filter_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    total_count: Mapped[int] = mapped_column(nullable=False, default=0)
    seen_count: Mapped[int] = mapped_column(nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", index=True)
    current_index: Mapped[int] = mapped_column(nullable=False, default=0)
    # v0.37：结束原因（COMPLETED / ABANDONED / EMPTY）；ACTIVE 时为 NULL。
    ended_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)


class ImageReviewSessionItem(Base):
    __tablename__ = "mobile_review_session_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("mobile_review_sessions.id"), nullable=False)
    item_index: Mapped[int] = mapped_column(nullable=False)
    image_id: Mapped[str] = mapped_column(ForeignKey("images.id"), nullable=False)
    seen: Mapped[bool] = mapped_column(nullable=False, default=False)
