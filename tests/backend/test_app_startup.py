"""后端应用可创建、可导入（Phase 0 验收：后端启动）。"""
from __future__ import annotations

from fastapi import FastAPI

from app.main import create_app


def test_create_app_returns_fastapi(settings):
    app = create_app(settings)
    assert isinstance(app, FastAPI)
    assert app.title == "NSFW Studio API"


def test_module_level_app_importable():
    from app.main import app as default_app

    assert default_app is not None


def test_lifespan_bootstrap_runs(client):
    """TestClient 进入上下文即触发 lifespan 启动引导，无异常即为通过。"""
    assert client.app is not None
