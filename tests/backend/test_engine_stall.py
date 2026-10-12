"""v0.13.2 (b) stall 卡死收敛测试（hermetic，假 adapter，不碰真引擎）。"""
from __future__ import annotations

import dataclasses

from app.core.config import Settings, WorkflowConfig


def make_snapshot(count: int = 1) -> dict:
    return {
        "prompt_mode": "structured",
        "structured_prompt": {"style": "anime", "scene": "cafe"},
        "full_prompt": "",
        "negative_prompt": "blurry",
        "selected_assets": {},
        "width": 512,
        "height": 768,
        "count": count,
        "seed_mode": "random",
        "workflow_modules": [],
    }


def mock_settings(settings: Settings) -> Settings:
    return dataclasses.replace(
        settings,
        workflow=WorkflowConfig(raw={
            "engine": {"provider": "mock", "options": {
                "worker_poll_interval_ms": 20, "engine_poll_ms": 20,
            }}
        }),
    )


def _wait(client, job_id, predicate, timeout=20.0):
    import time
    t0 = time.monotonic()
    last = None
    while time.monotonic() - t0 < timeout:
        r = client.get(f"/api/v1/jobs/{job_id}")
        last = r.json()
        if predicate(last):
            return last
        time.sleep(0.05)
    raise AssertionError(f"wait timeout: {last}")


def test_stall_zero_progress_times_out_and_fails_item(settings, monkeypatch):
    """引擎在线但 progress 持续 0 超过 stall_timeout → item FAILED(ENGINE_STALLED) + 调 interrupt/cancel。"""
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.engine.base import EngineJobStatus
    from app.engine.mock import MockEngineAdapter

    cancelled: list[str] = []

    async def fake_status(self, engine_job_id):
        return EngineJobStatus(state="running", progress=0.0, stage="")

    async def fake_cancel(self, engine_job_id):
        cancelled.append(engine_job_id)

    monkeypatch.setattr(MockEngineAdapter, "get_job_status", fake_status)
    monkeypatch.setattr(MockEngineAdapter, "cancel_job", fake_cancel)

    app = create_app(mock_settings(settings))
    with TestClient(app) as client:
        # 缩短 stall 超时，便于测试
        client.app.state.worker._stall_timeout = 0.3
        job = client.post("/api/v1/jobs", json={"snapshot": make_snapshot(1)}).json()
        final = _wait(client, job["id"],
                      lambda j: j["status"] in ("FAILED", "COMPLETED", "CANCELLED"),
                      timeout=20.0)
        # 必须判 FAILED 且 error_type=ENGINE_STALLED
        assert final["status"] == "FAILED", final
        items = [it for st in final["stages"] for it in st["items"]]
        assert any((it.get("error_type") == "ENGINE_STALLED"
                    or "STALLED" in str(it.get("error_message", ""))) for it in items), items
        # 必须调过一次 cancel/interrupt
        assert len(cancelled) >= 1


def test_slow_progress_no_stall(settings, monkeypatch):
    """progress 缓慢增长（虽慢但在动）→ 不判 stall，最终能完成。"""
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.engine.base import EngineJobStatus, EngineOutputFile
    from app.engine.mock import PNG_FIXTURE, MockEngineAdapter

    calls = {"n": 0}

    async def fake_status(self, engine_job_id):
        calls["n"] += 1
        if calls["n"] < 5:
            return EngineJobStatus(state="running", progress=0.1 * calls["n"], stage="model_loading")
        return EngineJobStatus(state="succeeded", progress=1.0, stage="save_image")

    async def fake_outputs(self, engine_job_id):
        return [EngineOutputFile(filename=f"{engine_job_id}.png", data=PNG_FIXTURE)]

    monkeypatch.setattr(MockEngineAdapter, "get_job_status", fake_status)
    monkeypatch.setattr(MockEngineAdapter, "get_job_outputs", fake_outputs)

    app = create_app(mock_settings(settings))
    with TestClient(app) as client:
        client.app.state.worker._stall_timeout = 0.3
        job = client.post("/api/v1/jobs", json={"snapshot": make_snapshot(1)}).json()
        final = _wait(client, job["id"],
                      lambda j: j["status"] in ("FAILED", "COMPLETED", "CANCELLED"),
                      timeout=20.0)
        assert final["status"] == "COMPLETED", final
