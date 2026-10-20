"""Prompt / PromptVersion 模型（Phase 1 规范 §六、§七）。

版本表创建后视为 immutable（§五十六）：Service 层禁止 UPDATE 版本内容。
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utc_now_iso
from app.database.base import Base


class Prompt(Base):
    __tablename__ = "prompts"
    __table_args__ = (CheckConstraint("status IN ('keep', 'candidate', 'eliminated')"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preview_image_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    favorite: Mapped[bool] = mapped_column(nullable=False, default=False)
    archived: Mapped[bool] = mapped_column(nullable=False, default=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="candidate", server_default="candidate")
    status_reason: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso, onupdate=utc_now_iso)

    versions: Mapped[list["PromptVersion"]] = relationship(
        back_populates="prompt",
        order_by="PromptVersion.version_no",
        cascade="all, delete-orphan",
    )


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (Index("uq_prompt_versions_no", "prompt_id", "version_no", unique=True),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    prompt_id: Mapped[str] = mapped_column(ForeignKey("prompts.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # structured | full
    positive_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    negative_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    structured_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utc_now_iso)

    prompt: Mapped[Prompt] = relationship(back_populates="versions")


class PromptEvaluation(Base):
    """人工评分记录；评分本身不触发提示词状态变更。"""

    __tablename__ = "prompt_evaluations"
    __table_args__ = (
        CheckConstraint("overall_score BETWEEN 1 AND 5"),
        Index("idx_prompt_evaluations_prompt_id", "prompt_id"),
        Index("idx_prompt_evaluations_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    prompt_id: Mapped[str] = mapped_column(ForeignKey("prompts.id"), nullable=False)
    prompt_version_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_versions.id"), nullable=True)
    overall_score: Mapped[int] = mapped_column(nullable=False)
    dimension_scores_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    source: Mapped[str] = mapped_column(Text, nullable=False, default="user", server_default="user")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now_iso)
