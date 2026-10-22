"""Agent / AI 提交契约（Phase 0.34）。

只允许单次文生图（基础生成 / 动漫）+ 可选高清放大；复杂链请用 UI。
安全边界：Bearer token（config.local `agent.token` 或环境变量）+ 每分钟限速；
8000 仍固定 loopback，不对公网暴露。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AgentJobRequest(BaseModel):
    """AI 助手（豆包/本地 Agent）提交一次生成请求。"""

    prompt: str = Field(min_length=1, max_length=10000, description="正向 Prompt（最终文本）")
    negative_prompt: str = Field(default="", max_length=8000, description="负向 Prompt")
    module_id: Literal["basic_generate", "anime_generate"] = Field(
        default="anime_generate",
        description="basic_generate=Qwen 写实；anime_generate=Anima 动漫",
    )
    upscale: bool = Field(default=False, description="生成后追加一次高清放大")
    width: int = Field(default=1024, ge=64, le=4096)
    height: int = Field(default=1024, ge=64, le=4096)
    count: int = Field(default=1, ge=1, le=64)
    seed: int | None = Field(default=None, ge=0, le=2147483647, description="固定 Seed；不传=随机")
    queue_mode: Literal["normal", "next"] = Field(default="normal", description="next=插队到当前任务之后")
    client_request_id: str | None = Field(
        default=None, max_length=128,
        description="幂等键：同一键重复提交返回原 Job（不重复生成）",
    )
