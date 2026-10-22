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

    def __init__(self, message: str | None = None, *, code: str | None = None,
                 details: dict | None = None) -> None:
        self.message = message or self.message
        if code:
            self.code = code
        # 可选结构化详情（Mobile Bridge envelope 的 error.details；Desktop 不使用）
        self.details = details
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


class UnauthorizedError(AppError):
    """缺少或无效凭据（Agent Bearer token / Mobile token）。"""

    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class TooManyRequestsError(AppError):
    """限速（Agent 提交频率）。"""

    status_code = 429
    code = "TOO_MANY_REQUESTS"


class FileValidationError(AppError):
    status_code = 400
    code = "INVALID_FILE"
