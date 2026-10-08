"""Image 模型（Phase 2C，规范 §四十一-§四十三）。

- file_path 为 DataRoot 相对路径（images/originals/<id>/...），禁止绝对路径；
- kind：original（Phase 2 实际产生）/ upscaled / processed（预留）；
- review_status：UNREVIEWED / KEPT / REJECTED；favorite 独立。
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import utc_now_iso
from app.database.base import Base

IMAGE_KINDS = ("original", "upscaled", "processed")
REVIEW_STATUSES = ("UNREVIEWED", "KEPT", "REJECTED")
IMAGE_SOURCES = ("comfyui", "mock", "import")


class Image(Base):
    __tablename__ = "images"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    job_item_id: Mapped[str | None] = mapped_column(ForeignKey("job_items.id"), nullable=True)
    parent_image_id: Mapped[str | None] = mapped_column(ForeignKey("images.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="original")
    file_path: Mapped[str] = mapped_column(Text, nullable=False)  # DataRoot 相对路径
    width: Mapped[int] = mapped_column(nullable=False)
    height: Mapped[int] = mapped_column(nullable=False)
    seed: Mapped[int | None] = mapped_column(nullable=True)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="UNREVIEWED")
    favorite: Mapped[bool] = mapped_column(nullable=False, default=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    # Phase 5：外部导入文件哈希（去重）与原始文件名（仅导入来源有值）
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    imported_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso, onupdate=utc_now_iso)
