"""Recipe / RecipeVersion / RecipeAssetSnapshot 模型（Phase 1 规范 §二十一-§二十六）。

- Recipe = 完整工作台配置快照（不是 Prompt 收藏）；
- Prompt 快照 + 来源 FK 同时保存：FK 知来源，快照保证历史不变；
- 素材快照按 slot 记录具体 asset_version_id，老素材升级不影响旧 RecipeVersion；
- slot 唯一约束：(recipe_version_id, slot)。
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utc_now_iso
from app.database.base import Base


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    favorite: Mapped[bool] = mapped_column(nullable=False, default=False)
    archived: Mapped[bool] = mapped_column(nullable=False, default=False)
    cover_image_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 图库阶段接入
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso, onupdate=utc_now_iso)

    versions: Mapped[list["RecipeVersion"]] = relationship(
        back_populates="recipe",
        order_by="RecipeVersion.version_no",
        cascade="all, delete-orphan",
    )


class RecipeVersion(Base):
    __tablename__ = "recipe_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    recipe_id: Mapped[str] = mapped_column(ForeignKey("recipes.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(nullable=False)

    prompt_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    positive_prompt_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    negative_prompt_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    structured_prompt_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    source_prompt_id: Mapped[str | None] = mapped_column(ForeignKey("prompts.id"), nullable=True)
    source_prompt_version_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_versions.id"), nullable=True)

    generation_settings_json: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default='{"modules":[]}')
    # Phase 5：输入图片快照（image_id + file hash + role；旧版本为空数组，绝不静默清空）
    input_images_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    default_count: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)

    recipe: Mapped[Recipe] = relationship(back_populates="versions")
    asset_snapshots: Mapped[list["RecipeAssetSnapshot"]] = relationship(
        back_populates="recipe_version",
        order_by="RecipeAssetSnapshot.slot",
        cascade="all, delete-orphan",
    )


class RecipeAssetSnapshot(Base):
    __tablename__ = "recipe_asset_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    recipe_version_id: Mapped[str] = mapped_column(ForeignKey("recipe_versions.id"), nullable=False)
    slot: Mapped[str] = mapped_column(String(16), nullable=False)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), nullable=False)
    asset_version_id: Mapped[str] = mapped_column(ForeignKey("asset_versions.id"), nullable=False)
    asset_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    preview_path_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)

    recipe_version: Mapped[RecipeVersion] = relationship(back_populates="asset_snapshots")
