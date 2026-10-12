"""ImageVariant 模型（Phase 0.11，图片变体系统）。

- 同一 Image 的 original / thumbnail / 未来 4K 等都作为该 Image 的 variant；
- 变体信息**不写回 images 表**，统一落在 image_variants；
- variant_type 第一版做 ``thumbnail``（512px WebP），预留 preview/upscaled/processed；
- path 为 DataRoot 相对路径（如 images/thumbnails/<image_id>/thumbnail.webp）。
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import utc_now_iso
from app.database.base import Base

VARIANT_TYPES = ("thumbnail", "preview", "upscaled", "processed")


class ImageVariant(Base):
    __tablename__ = "image_variants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    image_id: Mapped[str] = mapped_column(ForeignKey("images.id"), nullable=False, index=True)
    variant_type: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)  # DataRoot 相对路径
    width: Mapped[int | None] = mapped_column(nullable=True)
    height: Mapped[int | None] = mapped_column(nullable=True)
    format: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)
