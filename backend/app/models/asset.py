"""Asset / AssetVersion 模型（Phase 1 规范 §十二-§十六）。

- type 固定四类：face / clothing / pose / scene，禁止扩展顶级类型；
- 素材不嵌套（Asset 不得引用另一个 Asset）；
- preview_path 保存 **DataRoot 相对路径**，禁止绝对路径入库；
- 版本创建后 immutable。
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utc_now_iso
from app.database.base import Base

ASSET_TYPES = ("face", "clothing", "pose", "scene")


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    favorite: Mapped[bool] = mapped_column(nullable=False, default=False)
    archived: Mapped[bool] = mapped_column(nullable=False, default=False)
    source_image_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 图库阶段接入
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso, onupdate=utc_now_iso)

    versions: Mapped[list["AssetVersion"]] = relationship(
        back_populates="asset",
        order_by="AssetVersion.version_no",
        cascade="all, delete-orphan",
    )


class AssetVersion(Base):
    __tablename__ = "asset_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    preview_path: Mapped[str | None] = mapped_column(Text, nullable=True)  # DataRoot 相对路径
    reference_images_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)

    asset: Mapped[Asset] = relationship(back_populates="versions")
