"""POST /api/v1/system/request-shutdown 端点测试（Phase 0.14 应用内自停桥）。

- 仅回环：非回环 403；
- 立即 202 {accepted:true,...}；
- helper 只拉起一次（幂等：重复调用不再拉起）；
- 后端自身绝不杀自己（只 detached 拉起 helper）。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.v1 import system as system_module
from app.core.errors import AppError


def _client(loopback: bool, tmp_path: Path, launched: list[str]) -> TestClient:
    app = FastAPI()

    @app.exception_handler(AppError)
    def _h(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    app.include_router(system_module.router, prefix="/api/v1")
    app.state.settings = SimpleNamespace(config_dir=tmp_path / "configs")

    system_module._request_is_loopback = lambda r: loopback

    def _launch(helper: str) -> None:
        launched.append(helper)

    system_module._launch_shutdown_helper = _launch
    return TestClient(app)


def test_request_shutdown_loopback_202(tmp_path):
    launched: list[str] = []
    client = _client(True, tmp_path, launched)
    resp = client.post("/api/v1/system/request-shutdown")
    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted"] is True
    assert body["already_pending"] is False
    assert body["helper_launched"] is True
    # 拉起的是 shutdown helper（一次性桥），不是后端自杀
    assert len(launched) == 1
    assert launched[0].replace("\\", "/").endswith("scripts/runtime/shutdown_helper.ps1")


def test_request_shutdown_idempotent_no_double_helper(tmp_path):
    launched: list[str] = []
    client = _client(True, tmp_path, launched)
    r1 = client.post("/api/v1/system/request-shutdown")
    r2 = client.post("/api/v1/system/request-shutdown")
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r2.json()["already_pending"] is True
    # helper 只拉起一次
    assert len(launched) == 1


def test_request_shutdown_non_loopback_403(tmp_path):
    launched: list[str] = []
    client = _client(False, tmp_path, launched)
    resp = client.post("/api/v1/system/request-shutdown")
    assert resp.status_code == 403
    assert launched == [], "非回环绝不拉起 helper"
