"""v0.15.1 sampling stall 卡死收敛测试（hermetic，假 adapter，不碰真引擎）。

sampling stall 与 general execution timeout 分离：
- 仅采样阶段（step/max_step 有值）且 step 长时间冻结 → ENGINE_STALLED；
- 模型加载 / VAE / 高清放大 / 保存等无 step 阶段不套短 stall（即使超过 stall_timeout），
  由执行总超时兜底，最终能正常完成。
"""
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


def test_sampling_step_frozen_stalls_and_fails_item(settings, monkeypatch):
    """采样 Step 停在 12/30（progress 0.4 不动）超过 stall_timeout → ENGINE_STALLED + cancel。"""
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.engine.base import EngineJobStatus
    from app.engine.mock import MockEngineAdapter

    cancelled: list[str] = []

    async def fake_status(self, engine_job_id):
        return EngineJobStatus(state="running", progress=0.4, stage="sampling", step=12, max_step=30)

    async def fake_cancel(self, engine_job_id):
        cancelled.append(engine_job_id)

    monkeypatch.setattr(MockEngineAdapter, "get_job_status", fake_status)
    monkeypatch.setattr(MockEngineAdapter, "cancel_job", fake_cancel)

    app = create_app(mock_settings(settings))
    with TestClient(app) as client:
        client.app.state.worker._stall_timeout = 0.3
        job = client.post("/api/v1/jobs", json={"snapshot": make_snapshot(1)}).json()
        final = _wait(client, job["id"],
                      lambda j: j["status"] in ("FAILED", "COMPLETED", "CANCELLED"),
                      timeout=20.0)
        assert final["status"] == "FAILED", final
        items = [it for st in final["stages"] for it in st["items"]]
        assert any(it.get("error_type") == "ENGINE_STALLED" for it in items), items
        assert any("12/30" in str(it.get("error_message", "")) for it in items), items
        assert len(cancelled) >= 1


def test_non_sampling_phase_not_short_stalled(settings, monkeypatch):
    """模型加载（无 step、progress 0）即使超过 stall_timeout 也不判短 stall，随后成功 → COMPLETED。"""
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.engine.base import EngineJobStatus, EngineOutputFile
    from app.engine.mock import PNG_FIXTURE, MockEngineAdapter

    calls = {"n": 0}

    async def fake_status(self, engine_job_id):
        calls["n"] += 1
        # 约 25 个 poll（每个 20ms ≈ 0.5s）停在无 step 的模型加载阶段，超过 stall_timeout=0.3
        if calls["n"] < 25:
            return EngineJobStatus(state="running", progress=0.0, stage="model_loading")
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


def test_sampling_step_advances_no_stall(settings, monkeypatch):
    """采样 step 持续推进（即使很慢）→ 不判 stall，最终完成。"""
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.engine.base import EngineJobStatus, EngineOutputFile
    from app.engine.mock import PNG_FIXTURE, MockEngineAdapter

    calls = {"n": 0}

    async def fake_status(self, engine_job_id):
        calls["n"] += 1
        if calls["n"] <= 3:
            return EngineJobStatus(
                state="running", progress=calls["n"] / 4, stage="sampling",
                step=calls["n"], max_step=4,
            )
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
