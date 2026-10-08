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


ASSET_REFERENCE_ROLES = ("face_reference",)


class AssetReferenceImage(Base):
    """素材参考图正式关系（Phase 5 §十二/§十三：不再把复杂关系长期塞 JSON）。

    - 归属具体 asset_version（版本不可变：参考图变化 = 新版本）；
    - image_id 指向图库 Image（不复制外部文件，统一走 image_id）；
    - Phase 5 仅 role=face_reference 且每版本一张；未来多图按 sort_order 扩展。
    """

    __tablename__ = "asset_reference_images"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_version_id: Mapped[str] = mapped_column(ForeignKey("asset_versions.id"), nullable=False)
    image_id: Mapped[str] = mapped_column(ForeignKey("images.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="face_reference")
    sort_order: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)
