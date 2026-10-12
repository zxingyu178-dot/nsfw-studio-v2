"""系统状态摘要出入参（Phase 0.12 Task7）。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SystemStatusResponse(BaseModel):
    """GET /api/v1/system/status 只读摘要（Settings 系统维护中心）。

    绝不包含任何敏感配置内容（token / 密码 / config.local）。
    """

    app_version: str
    data_root: str
    database_path: str
    database_size: int  # studio.db 文件字节数
    disk_total: int     # DataRoot 所在磁盘总字节
    disk_free: int     # DataRoot 所在磁盘可用字节
    image_count: int
    thumbnail_count: int
    preview_count: int
    latest_migration: str | None
    # 复用现有 EngineRuntimeService 状态摘要（state/host/port/owned/pid/...）
    engine_runtime: dict[str, Any]
