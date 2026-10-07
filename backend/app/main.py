"""NSFW Studio 后端入口。

- ``create_app(settings)`` 工厂：测试可注入临时配置；
- lifespan 中执行启动引导（数据目录 / 日志 / 数据库）并建立请求级 session 工厂；
- 统一错误格式（Phase 1 规范 §三十六）：``{"error": {"code", "message"}}``；
- 本文件不包含任何生成引擎相关配置（不绑定 ComfyUI）。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from app.api.v1.router import api_v1_router
from app.core.config import Settings, load_settings
from app.core.errors import AppError
from app.database.base import make_engine, make_session_factory
from app.services.system_service import bootstrap
from app.storage.manager import StorageManager

logger = logging.getLogger(__name__)


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings: Settings = application.state.settings
    report = bootstrap(settings)

    engine = make_engine(report.database_path)
    application.state.engine = engine
    application.state.session_factory = make_session_factory(engine)
    application.state.storage = StorageManager(settings)

    logging.getLogger(__name__).info(
        "后端启动完成 version=%s data_root=%s", settings.app.version, report.data_root
    )
    yield
    engine.dispose()
    logging.getLogger(__name__).info("后端停止")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    application = FastAPI(title="NSFW Studio API", version=settings.app.version, lifespan=lifespan)
    application.state.settings = settings

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ===== 统一错误格式（Phase 1 规范 §三十六） =====
    @application.exception_handler(AppError)
    def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message)

    @application.exception_handler(RequestValidationError)
    def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        message = f"参数校验失败: {location} {first.get('msg', '')}".strip()
        return _error_response(422, "VALIDATION_ERROR", message)

    @application.exception_handler(Exception)
    def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常: %s", exc)
        return _error_response(500, "INTERNAL_ERROR", "服务器内部错误")

    application.include_router(api_v1_router)

    @application.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"name": settings.app.name, "version": settings.app.version, "api": "/api/v1/health"}

    return application


app = create_app()
