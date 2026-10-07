"""Phase 2.2 数据一致性与恢复收口回归（§2 恢复终态归并 / §3 Resume 身份继承）。

§1 批次原子导入在 test_image_service.py；§4 取消边界在 test_comfyui_resilience.py。
全部离线可跑（Mock 引擎 + stub），无需真实 ComfyUI。
"""
from __future__ import annotations

import dataclasses
import json
import time

import pytest
from sqlalchemy import select

from app.core.config import Settings, WorkflowConfig
from app.main import create_app


def mock_settings(settings: Settings, **options) -> Settings:
    merged = {"worker_poll_interval_ms": 20, "engine_poll_ms": 20}
    merged.update(options)
    return dataclasses.replace(
        settings,
        workflow=WorkflowConfig(raw={"engine": {"provider": "mock", "options": merged}}),
    )


def wait_for(client, job_id, predicate, timeout=20.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/api/v1/jobs/{job_id}").json()
        if predicate(last):
            return last
        time.sleep(0.05)
    raise AssertionError(f"等待任务状态超时: {json.dumps(last, ensure_ascii=False)[:400]}")


def make_snapshot(count=1, **overrides):
    snapshot = {
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
    snapshot.update(overrides)
    return snapshot


async def _noop_stop(timeout: float = 10.0) -> None:  # 跳过优雅收尾，制造"进程崩溃"现场
    return None


# ===== §2：恢复成功后 Job 必须正确归并终态 =====

def test_recovery_completes_job_after_crash_case_a(settings, monkeypatch):
    """Case A：1 张任务，崩溃后引擎已完成 → Item COMPLETED 且 Job COMPLETED。"""
    from fastapi.testclient import TestClient

    from app.engine.base import EngineJobStatus, EngineOutputFile
    from app.engine.mock import PNG_FIXTURE, MockEngineAdapter
    from app.models import JobEvent

    app = create_app(mock_settings(settings))
    with TestClient(app) as client:
        client.app.state.adapter.delay_per_item_ms = 300
        job = client.post("/api/v1/jobs", json={"snapshot": make_snapshot()}).json()
        wait_for(client, job["id"], lambda j: j["status"] == "RUNNING")
        job_id = job["id"]
        client.app.state.adapter.delay_per_item_ms = 15_000  # 卡住轮询，避免收尾时恰好完成
        client.app.state.worker.stop = _noop_stop  # 模拟崩溃（不等待 Worker 收尾）
        engine = client.app.state.engine
    engine.dispose()

    # "引擎侧其实已完成"：重启后的 Adapter 能确认 succeeded 并给出输出
    async def fake_status(self, engine_job_id):
        return EngineJobStatus(state="succeeded", progress=1.0, stage="save_image")

    async def fake_outputs(self, engine_job_id):
        return [EngineOutputFile(filename=f"{engine_job_id}.png", data=PNG_FIXTURE)]

    monkeypatch.setattr(MockEngineAdapter, "get_job_status", fake_status)
    monkeypatch.setattr(MockEngineAdapter, "get_job_outputs", fake_outputs)

    app2 = create_app(mock_settings(settings))
    with TestClient(app2) as client2:
        detail = wait_for(client2, job_id, lambda j: j["status"] == "COMPLETED", timeout=20)
        assert detail["completed_count"] == 1, "全部 Item COMPLETED 时 completed_count 必须正确"
        assert detail["items"][0]["status"] == "COMPLETED"
        assert detail["items"][0]["image_id"], "恢复也必须导入图片（§2.1 完成条件）"
        assert detail["finished_at"], "Job COMPLETED 必须写入 finished_at"

        with client2.app.state.session_factory() as session:
            events = session.execute(
                select(JobEvent).where(JobEvent.job_id == job_id)
            ).scalars().all()
            types = [event.event_type for event in events]
        assert "JOB_RECOVERED_COMPLETED" in types, "恢复完成必须记录 JOB_RECOVERED_COMPLETED 事件"


def test_recovery_keeps_interrupted_with_correct_count_case_b(settings):
    """Case B：3 张任务，2 张已完成，第 3 张无法确认 → Job INTERRUPTED，completed_count=2。"""
    from fastapi.testclient import TestClient

    app = create_app(mock_settings(settings))
    with TestClient(app) as client:
        adapter = client.app.state.adapter
        adapter.delay_per_item_ms = 60
        job = client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=3)}).json()
        job_id = job["id"]
        wait_for(client, job_id, lambda j: j["status"] == "RUNNING" and j["completed_count"] >= 2,
                 timeout=20)
        adapter.delay_per_item_ms = 15_000
        client.app.state.worker.stop = _noop_stop
        engine = client.app.state.engine
    engine.dispose()

    app2 = create_app(mock_settings(settings))
    with TestClient(app2) as client2:
        detail = wait_for(client2, job_id, lambda j: j["status"] != "RUNNING", timeout=20)
        assert detail["status"] == "INTERRUPTED", "无法确认的剩余图片必须保持可恢复状态"
        assert detail["completed_count"] == 2
        statuses = [item["status"] for item in detail["items"]]
        assert statuses.count("COMPLETED") == 2
        assert "RUNNING" not in statuses
        assert statuses[2] in ("QUEUED", "INTERRUPTED")


# ===== §3：Resume 必须保持原 Workflow 身份 =====

@pytest.fixture()
def mock_client(settings):
    from fastapi.testclient import TestClient

    app = create_app(mock_settings(settings))
    with TestClient(app) as test_client:
        yield test_client


def test_resume_inherits_parent_workflow_identity(mock_client):
    """Parent=v1，当前系统升级为 v2 → Child 的 Workflow 身份必须仍完整等于 Parent（v1）。"""
    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=3)}).json()
    wait_for(mock_client, job["id"],
             lambda j: j["status"] == "RUNNING" and j["completed_count"] >= 1)
    mock_client.post(f"/api/v1/jobs/{job['id']}/cancel")
    parent = wait_for(mock_client, job["id"], lambda j: j["status"] == "CANCELLED")
    assert parent["requested_count"] > parent["completed_count"], "必须还有剩余图片才能续跑"
    parent_modules = parent["workflow_snapshot"]["modules"]
    assert parent_modules and parent_modules[0]["module_version"] == "v1"

    # 模拟系统 Workflow 升级到 v2（仅改内存配置）
    engine_cfg = mock_client.app.state.settings.workflow.raw["engine"]
    engine_cfg["module_version"] = "v2"
    engine_cfg["binding_version"] = "v2"
    try:
        fresh = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot()}).json()
        assert fresh["workflow_snapshot"]["modules"][0]["module_version"] == "v2", \
            "升级后新创建的 Job 才应使用当前 v2 身份"

        child = mock_client.post(f"/api/v1/jobs/{job['id']}/resume-remaining").json()
        child_modules = child["workflow_snapshot"]["modules"]
        assert child_modules == parent_modules, "Resume 必须完整继承 Parent 的 workflow_snapshot"
        assert child["module_id"] == parent["module_id"]
        assert child["module_version"] == parent["module_version"] == "v1"
        assert child["binding_version"] == parent["binding_version"] == "v1"
        assert child["provider"] == parent["provider"]
        assert child["workflow_hash"] == parent["workflow_hash"]
        # 数据库列 == workflow_snapshot.modules[0]（禁止两处不一致）
        assert child_modules[0]["module_id"] == child["module_id"]
        assert child_modules[0]["module_version"] == child["module_version"]
        assert child_modules[0]["binding_version"] == child["binding_version"]
        assert child_modules[0]["provider"] == child["provider"]

        child_final = wait_for(mock_client, child["id"], lambda j: j["status"] == "COMPLETED",
                               timeout=30)
        assert child_final["module_version"] == "v1", "执行完成也不得静默升级到 v2"
    finally:
        engine_cfg.pop("module_version", None)
        engine_cfg.pop("binding_version", None)