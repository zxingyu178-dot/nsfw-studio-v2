"""API 公共数据结构。"""
from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """统一错误格式（Phase 1 规范 §三十六）。"""

    error: ErrorBody


class ListMeta(BaseModel):
    total: int
    limit: int
    offset: int
