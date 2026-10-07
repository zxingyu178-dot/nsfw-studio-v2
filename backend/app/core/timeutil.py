"""统一业务时间工具（Phase 1 规范 §五）。

全部业务时间使用 **UTC + ISO 8601**，例如 ``2026-10-07T07:30:12.123Z``。
禁止各模块自行 ``datetime.now()`` 生成不同格式。
"""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """当前 UTC 时间，ISO 8601 毫秒精度，Z 结尾。"""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
