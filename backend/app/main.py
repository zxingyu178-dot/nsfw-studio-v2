"""NSFW Studio 后端入口。

- ``create_app(settings)`` 工厂：测试可注入临时配置；
- lifespan 中执行启动引导（数据目录 / 日志 / 数据库，Phase 0 规范 §九、§十）；
- 本文件不包含任何生成引擎相关配置（Phase 0 不绑定 ComfyUI）。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import Settings, load_settings
from app.services.system_service import bootstrap


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings: Settings = application.state.settings
    report = bootstrap(settings)
    application.state.bootstrap_report = report
    logging.getLogger(__name__).info("后端启动完成 version=%s data_root=%s", settings.app.version, report.data_root)
    yield
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

    application.include_router(api_v1_router)

    @application.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"name": settings.app.name, "version": settings.app.version, "api": "/api/v1/health"}

    return application


app = create_app()
