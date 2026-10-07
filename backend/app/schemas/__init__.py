"""API 出入参数据结构（Pydantic）。

Phase 0 仅有健康检查；Phase 1 规划：CreateJobRequest / JobResponse 等
（见 docs/API_PLAN.md）。
"""
from app.schemas.health import HealthResponse

__all__ = ["HealthResponse"]
