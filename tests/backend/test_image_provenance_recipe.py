"""Phase 0.12 Task12：Image Provenance（轻量）—— WorkbenchSnapshot.source_recipe_* 测试。

语义：工作台最初从哪个 Recipe 打开（非永久强绑定）。
- 从 Recipe 打开后提交 Job → workbench_snapshot 冻结来源 recipe；
- 经 Image → Job.workbench_snapshot_json 可读回（Lightbox 展示"来源 Recipe"）；
- 非 Recipe 来源 → 两字段为 None（前端隐藏该行，绝不伪造）。
"""
from __future__ import annotations

import dataclasses
import time

import pytest

from app.core.config import Settings, WorkflowConfig
from app.main import create_app


def mock_settings(settings: Settings) -> Settings:
    return dataclasses.replace(
        settings,
        workflow=WorkflowConfig(raw={
            "engine": {"provider": "mock",
                       "options": {"worker_poll_interval_ms": 20, "engine_poll_ms": 20}}},
        ),
    )


@pytest.fixture()
def mock_client(settings):
    from fastapi.testclient import TestClient

    app = create_app(mock_settings(settings))
    with TestClient(app) as test_client:
        yield test_client


def make_snapshot(count=1, **overrides) -> dict:
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


def wait_for(client, job_id, timeout=60.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/api/v1/jobs/{job_id}").json()
        if last["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            return last
        time.sleep(0.05)
    raise AssertionError(f"等待任务完成超时: {last}")


def _original_image(client, job_id: str) -> dict:
    items = client.get("/api/v1/images", params={"job_id": job_id, "limit": 200}).json()["items"]
    return next(i for i in items if i["kind"] == "original")


def test_snapshot_model_accepts_source_recipe_fields():
    """契约层：WorkbenchSnapshotModel 接受两个可选 provenance 字段，默认 None。"""
    from app.schemas.workbench import WorkbenchSnapshotModel

    plain = WorkbenchSnapshotModel()
    assert plain.source_recipe_id is None
    assert plain.source_recipe_version_id is None

    stamped = WorkbenchSnapshotModel(source_recipe_id="rcp-1", source_recipe_version_id="ver-9")
    dumped = stamped.model_dump()
    assert dumped["source_recipe_id"] == "rcp-1"
    assert dumped["source_recipe_version_id"] == "ver-9"


def test_recipe_provenance_survives_job_freeze_and_readback(mock_client):
    # 1) 建一个真实 Recipe（模拟"从 Recipe 打开工作台"的来源）
    recipe = mock_client.post("/api/v1/recipes", json={
        "name": "来源配方",
        "snapshot": make_snapshot(),
    }).json()
    recipe_id = recipe["id"]
    version_id = recipe["current_version"]["id"]

    # 2) 从该 Recipe 打开工作台 → 提交 Job（snapshot 携带来源 recipe 身份）
    snapshot = make_snapshot(source_recipe_id=recipe_id, source_recipe_version_id=version_id)
    job = mock_client.post("/api/v1/jobs", json={"snapshot": snapshot}).json()
    final = wait_for(mock_client, job["id"])
    assert final["status"] == "COMPLETED"

    original = _original_image(mock_client, job["id"])

    # 3) Image → Job.workbench_snapshot_json 可读回来源 Recipe
    prov = mock_client.get(f"/api/v1/images/{original['id']}/provenance").json()
    assert prov["source_recipe_id"] == recipe_id
    assert prov["source_recipe_version_id"] == version_id


def test_non_recipe_workbench_provenance_is_null(mock_client):
    # 全新工作台（未从 Recipe 打开）→ 来源 Recipe 两字段为 None，绝不伪造
    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot()}).json()
    wait_for(mock_client, job["id"])
    original = _original_image(mock_client, job["id"])

    prov = mock_client.get(f"/api/v1/images/{original['id']}/provenance").json()
    assert prov["source_recipe_id"] is None
    assert prov["source_recipe_version_id"] is None
