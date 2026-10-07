"""Prompt / PromptVersion 模型（Phase 1 规范 §六、§七）。

版本表创建后视为 immutable（§五十六）：Service 层禁止 UPDATE 版本内容。
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utc_now_iso
from app.database.base import Base


class Prompt(Base):
    __tablename__ = "prompts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    favorite: Mapped[bool] = mapped_column(nullable=False, default=False)
    archived: Mapped[bool] = mapped_column(nullable=False, default=False)
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
