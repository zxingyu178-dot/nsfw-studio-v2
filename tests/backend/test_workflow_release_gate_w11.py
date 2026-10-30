"""W1.1-1：服务端正式放行门禁（新任务拒绝 / 历史恢复不受影响）。

- POST /jobs：未放行 anime、未登记 binding 均 400 WORKFLOW_NOT_RELEASED；
- 正常 basic_generate 与 img2img v2 可提交；
- 拒绝时数据库不产生残留 Job；
- /jobs/{id}/resume-remaining（从 History 创建新 Job）受门禁；
- /jobs/resume-interrupted（可信恢复通道）不受新门禁破坏。
"""
from __future__ import annotations

import dataclasses
import json
import time

import pytest

from app.core.config import Settings, WorkflowConfig
from app.engine import release
from app.main import create_app
from app.models import Job
from app.services import job_service


def make_snapshot(count: int = 1, **overrides) -> dict:
    snapshot = {
        "prompt_mode": "full",
        "full_prompt": "1girl, silver hair, studio portrait",
        "negative_prompt": "blurry",
        "count": count,
        "width": 768,
        "height": 768,
        "seed_mode": "random",
        "workflow_modules": [],
    }
    snapshot.update(overrides)
    return snapshot


def mock_settings(settings: Settings, **options) -> Settings:
    merged = {"worker_poll_interval_ms": 20, "engine_poll_ms": 20}
    merged.update(options)
    return dataclasses.replace(
        settings,
        workflow=WorkflowConfig(raw={
            "engine": {
                "provider": "mock",
                "options": merged,
                # 与 configs/workflow.yaml 一致：img2img 新任务默认 v2
                "modules": {"img2img": {"binding_version": "v2"}},
            },
        }),
    )


@pytest.fixture()
def mock_client(settings):
    from fastapi.testclient import TestClient

    app = create_app(mock_settings(settings))
    with TestClient(app) as test_client:
        yield test_client


def job_count(session) -> int:
    return session.query(Job).count()


def test_unreleased_anime_rejected_without_job_residue(mock_client, monkeypatch, session):
    """用临时 manifest 把 anime 标记为未放行，验证门禁本身（生产清单按真实证据另行登记）。"""
    monkeypatch.setattr(release, "load_release_manifest", lambda: {"modules": {
        "anime_generate": {"bindings": {"v1": {
            "dependencies_ready": True,
            "real_gate_passed": False,
            "hardware_status": "experimental",
            "default_profile_verified": False,
            "notes": "test-only unreleased",
        }}},
    }})
    before = job_count(session)
    response = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(workflow_modules=[{"module_id": "anime_generate"}]),
    })
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "WORKFLOW_NOT_RELEASED"
    assert job_count(session) == before, "拒绝后不得产生残留 Job"


def test_unregistered_binding_rejected(mock_client, monkeypatch, session):
    monkeypatch.setattr(release, "load_release_manifest", lambda: {"modules": {}})
    before = job_count(session)
    response = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(workflow_modules=[{"module_id": "basic_generate"}]),
    })
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "WORKFLOW_NOT_RELEASED"
    assert job_count(session) == before


def test_released_basic_generate_accepted(mock_client):
    response = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(workflow_modules=[{"module_id": "basic_generate"}]),
    })
    assert response.status_code == 201, response.text
    assert response.json()["workflow_snapshot"]["modules"][0]["binding_version"] == "v1"


def test_released_img2img_v2_accepted(mock_client, png_bytes):
    imported = mock_client.post(
        "/api/v1/images/import", files=[("files", ("w11_img.png", png_bytes, "image/png"))]
    )
    assert imported.status_code == 201, imported.text
    image = imported.json()["imported"][0]["image"]
    response = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(
            input_images=[{"role": "source", "image_id": image["id"]}],
            workflow_modules=[{"module_id": "img2img"}],
        ),
    })
    assert response.status_code == 201, response.text
    assert response.json()["workflow_snapshot"]["modules"][0]["binding_version"] == "v2"


def test_history_resume_remaining_is_gated(mock_client, monkeypatch, session):
    # 暂停队列，避免 Mock Worker 把测试用 Job 跑掉
    assert mock_client.post("/api/v1/queue/pause").status_code == 200
    fingerprint_modules = [{
        "module_id": "basic_generate",
        "module_version": "v1",
        "provider": "mock",
        "binding_version": "v1",
        "workflow_hash": None,
        "binding_hash": None,
    }]
    job, _ = job_service.create_job(
        session,
        source="web",
        snapshot=make_snapshot(count=2, workflow_modules=[{"module_id": "basic_generate"}]),
        workflow_modules=fingerprint_modules,
        job_kind="generate",
    )
    job.status = "FAILED"
    session.commit()

    monkeypatch.setattr(release, "load_release_manifest", lambda: {"modules": {}})
    before_children = session.query(Job).filter(Job.resume_of_job_id == job.id).count()
    response = mock_client.post(f"/api/v1/jobs/{job.id}/resume-remaining")
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "WORKFLOW_NOT_RELEASED"
    assert session.query(Job).filter(Job.resume_of_job_id == job.id).count() == before_children


def test_interrupted_recovery_is_not_gated(mock_client, session):
    """可信恢复通道：即使 anime 未放行，INTERRUPTED 恢复仍按原 Job 身份重排队。"""
    assert mock_client.post("/api/v1/queue/pause").status_code == 200
    modules = [{
        "module_id": "anime_generate",
        "module_version": "v1",
        "provider": "mock",
        "binding_version": "v1",
        "workflow_hash": None,
        "binding_hash": None,
    }]
    job, _ = job_service.create_job(
        session,
        source="web",
        snapshot=make_snapshot(count=1, workflow_modules=[{"module_id": "anime_generate"}]),
        workflow_modules=modules,
        job_kind="generate",
    )
    job.status = "INTERRUPTED"
    session.commit()

    response = mock_client.post("/api/v1/jobs/resume-interrupted")
    assert response.status_code == 200, response.text
    result = response.json()
    assert job.id in result["requeued"], json.dumps(result, ensure_ascii=False)[:500]
