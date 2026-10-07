"""统一业务异常与 API 错误格式（Phase 1 规范 §三十六）。

API 错误响应统一为::

    {"error": {"code": "ASSET_NOT_FOUND", "message": "素材不存在"}}

禁止各接口自行使用不同错误格式。Router 不直接构造错误响应，
而是抛出本模块异常，由全局 handler 转换。
"""
from __future__ import annotations


class AppError(Exception):
    """业务异常基类。"""

    status_code = 400
    code = "APP_ERROR"
    message = "请求处理失败"

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        self.message = message or self.message
        if code:
            self.code = code
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ValidationError(AppError):
    status_code = 400
    code = "VALIDATION_ERROR"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class FileValidationError(AppError):
    status_code = 400
    code = "INVALID_FILE"
