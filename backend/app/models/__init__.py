"""数据库模型层。

Phase 0 仅有 ``SystemInfo``；Phase 1 规划：Job / JobItem / Prompt / Recipe / Asset / Image
（字段设计见 docs/DATABASE_PLAN.md）。
"""
from app.models.system import SystemInfo

__all__ = ["SystemInfo"]
