"""健康检查响应结构（Phase 0 规范 §十五）。"""
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str
