"""生产环境静态托管（日用模式：FastAPI 直接托管 React 构建产物 ``frontend/dist``）。

注册顺序（在 ``create_app`` 中、include API router 之后调用）：

1. ``/assets`` → ``<dist>/assets``（``fastapi.staticfiles.StaticFiles(html=True)``）；
2. SPA catch-all ``GET /{full_path:path}``：非 API 的客户端路由（``/``、``/generate``、
   ``/gallery``、``/prompts``、``/settings`` 及任意深层路径）返回 ``dist/index.html``(200)；
   若 ``full_path`` 以 ``"api/"`` 开头，返回 404 JSON，绝不能把 index.html 返回给 ``/api``。

当 ``dist/index.html`` 不存在时（开发 / 测试环境）：本函数不注册任何路由，
返回 ``False``，由 ``create_app`` 保持原有 ``GET /`` 返回 JSON 的行为，
保证开发（Vite 5173 + proxy）与测试环境不破。
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# backend/app/core/static_hosting.py -> parents: [core, app, backend, 项目根]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"


def register_static_hosting(app: FastAPI, dist_dir: str | Path | None = None) -> bool:
    """在应用上注册生产静态托管。

    Args:
        app: FastAPI 应用实例。
        dist_dir: React 构建产物目录；默认为 ``<PROJECT_ROOT>/frontend/dist``。

    Returns:
        是否启用了 SPA 托管。``False`` 表示 dist 缺失，调用方应保留 JSON 根路由。
    """
    dist = Path(dist_dir) if dist_dir is not None else DEFAULT_DIST_DIR
    index_file = dist / "index.html"
    if not index_file.is_file():
        logger.info("静态托管未启用：未找到 %s（开发/测试模式，保留 JSON 根路由）", index_file)
        return False

    assets_dir = dist / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(assets_dir), html=True),
            name="spa-assets",
        )

    @app.get("/", include_in_schema=False)
    def _spa_root():
        return FileResponse(str(index_file))

    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa_catch_all(full_path: str):
        # API 不得被吞：未匹配到 API 路由的 /api/* 必须返回 404 JSON，而非 index.html
        if full_path.startswith("api/"):
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "NOT_FOUND", "message": "Not Found"}},
            )
        return FileResponse(str(index_file))

    logger.info("静态托管已启用：%s", dist)
    return True
