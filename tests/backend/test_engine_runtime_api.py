"""受管 ComfyUI 运行时 API 契约测试（Commit 3）。

用 fake 服务替换 app.state.engine_runtime，验证冻结返回体与 409 错误信封：
- GET runtime 结构；
- start/stop/restart 返回契约体；
- external 的 stop/restart → 409 ENGINE_NOT_OWNED；
- PORT_CONFLICT 的 start → 409 ENGINE_PORT_CONFLICT；
- 幂等 start 为 200。
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.v1 import engine_runtime
from app.core.errors import AppError
from app.services.engine_runtime_service import (
    EngineNotOwned,
    EnginePortConflict,
    RuntimeSnapshot,
)


def _snapshot(state: str, owned: bool, pid=None) -> RuntimeSnapshot:
    return RuntimeSnapshot(
        state=state,
        host="127.0.0.1",
        port=8188,
        owned=owned,
        pid=pid,
        started_at="2026-10-11T00:00:00+00:00" if pid else None,
        detail="d",
        log_location="C:/x/comfyui-managed.log",
        health={"online": owned, "engine_name": "comfyui", "engine_version": "0.3.0"},
    )


class FakeService:
    def __init__(self):
        self.status_snap = _snapshot("STOPPED", False, None)
        self.start_snap = _snapshot("RUNNING_MANAGED", True, 9999)
        self.stop_snap = _snapshot("STOPPED", False, None)
        self.restart_snap = _snapshot("RUNNING_MANAGED", True, 8888)
        self.start_calls = 0
        self.raise_not_owned = False
        self.raise_port_conflict = False

    def status(self):
        return self.status_snap

    def start(self):
        self.start_calls += 1
        if self.raise_port_conflict:
            raise EnginePortConflict()
        return self.start_snap

    def stop(self):
        if self.raise_not_owned:
            raise EngineNotOwned()
        return self.stop_snap

    def restart(self):
        if self.raise_not_owned:
            raise EngineNotOwned()
        return self.restart_snap


def _client(svc: FakeService) -> TestClient:
    from fastapi import APIRouter

    app = FastAPI()

    @app.exception_handler(AppError)
    def _h(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    parent = APIRouter(prefix="/api/v1")
    parent.include_router(engine_runtime.router)
    app.include_router(parent)
    app.state.engine_runtime = svc
    return TestClient(app)


def test_get_runtime_structure():
    svc = FakeService()
    svc.status_snap = _snapshot("RUNNING_MANAGED", True, 1234)
    client = _client(svc)
    resp = client.get("/api/v1/engine/runtime")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "state", "host", "port", "owned", "pid",
        "started_at", "detail", "log_location", "health",
    }
    assert body["state"] == "RUNNING_MANAGED"
    assert body["host"] == "127.0.0.1"
    assert body["port"] == 8188
    assert body["owned"] is True
    assert body["pid"] == 1234
    assert set(body["health"].keys()) == {"online", "engine_name", "engine_version"}


def test_start_stop_restart_contract_body():
    svc = FakeService()
    client = _client(svc)
    for method, path in [
        ("POST", "/api/v1/engine/runtime/start"),
        ("POST", "/api/v1/engine/runtime/stop"),
        ("POST", "/api/v1/engine/runtime/restart"),
    ]:
        resp = getattr(client, method.lower())(path)
        assert resp.status_code == 200, path
        body = resp.json()
        assert set(body.keys()) == {
            "state", "host", "port", "owned", "pid",
            "started_at", "detail", "log_location", "health",
        }


def test_external_stop_restart_409_not_owned():
    svc = FakeService()
    svc.raise_not_owned = True
    client = _client(svc)
    for path in ("/api/v1/engine/runtime/stop", "/api/v1/engine/runtime/restart"):
        resp = client.post(path)
        assert resp.status_code == 409, path
        assert resp.json()["error"]["code"] == "ENGINE_NOT_OWNED"


def test_port_conflict_start_409():
    svc = FakeService()
    svc.raise_port_conflict = True
    client = _client(svc)
    resp = client.post("/api/v1/engine/runtime/start")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ENGINE_PORT_CONFLICT"


def test_idempotent_start_200():
    svc = FakeService()
    client = _client(svc)
    r1 = client.post("/api/v1/engine/runtime/start")
    r2 = client.post("/api/v1/engine/runtime/start")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert svc.start_calls == 2  # fake 每次都返回运行态；真实服务在 RUNNING 下短路不 spawn
