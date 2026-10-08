"""Phase 4 测试：History（Task5/6）、派生图 → 工作台追溯（Task7）、
Workflow 身份恢复（Task9）、Image Provenance（Task10）。全部离线可跑（Mock 引擎）。
"""
from __future__ import annotations

import dataclasses
import json
import time

import pytest

from app.core.config import Settings, WorkflowConfig
from app.main import create_app


def mock_settings(settings: Settings, **options) -> Settings:
    merged = {"worker_poll_interval_ms": 20, "engine_poll_ms": 20}
    merged.update(options)
    return dataclasses.replace(
        settings,
        workflow=WorkflowConfig(raw={"engine": {"provider": "mock", "options": merged}}),
    )


def wait_for(client, job_id, predicate, timeout=60.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/api/v1/jobs/{job_id}").json()
        if predicate(last):
            return last
        time.sleep(0.05)
    raise AssertionError(f"等待任务状态超时: {json.dumps(last, ensure_ascii=False)[:500]}")


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


def pipeline_snapshot(count=1):
    snapshot = make_snapshot(count=count)
    snapshot["workflow_modules"] = [{"module_id": "basic_generate"}, {"module_id": "upscale"}]
    return snapshot


@pytest.fixture()
def mock_client(settings):
    from fastapi.testclient import TestClient

    app = create_app(mock_settings(settings))
    with TestClient(app) as test_client:
        yield test_client


def gallery(client, job_id: str) -> list[dict]:
    return client.get("/api/v1/images", params={"job_id": job_id, "limit": 200}).json()["items"]


def history(client, **params) -> dict:
    return client.get("/api/v1/history", params=params).json()


def find_family(client, root_id: str, **params) -> dict | None:
    page = history(client, **params)
    return next((item for item in page["items"] if item["root_job_id"] == root_id), None)


# ===== Task5/6：History 来源 = jobs；原任务 + 续跑两级归组；基础筛选 =====

def test_history_lists_web_and_resume_family_with_filters(mock_client):
    adapter = mock_client.app.state.adapter
    adapter.fail_after_items = 1  # 第 2 次提交开始失败 → Job A 部分失败
    try:
        job_a = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=2)}).json()
        final_a = wait_for(mock_client, job_a["id"], lambda j: j["status"] == "FAILED")
        assert final_a["completed_count"] == 1

        # A FAILED → 续跑剩余 → B（也失败，制造两级链）
        adapter.fail_after_items = 2
        job_b = mock_client.post(f"/api/v1/jobs/{job_a['id']}/resume-remaining").json()
        assert job_b["source"] == "resume" and job_b["resume_of_job_id"] == job_a["id"]
        wait_for(mock_client, job_b["id"], lambda j: j["status"] == "FAILED")

        # B FAILED → 再续跑 → C（成功）：仍归入同一任务族（禁止复杂树）
        adapter.fail_after_items = 0
        job_c = mock_client.post(f"/api/v1/jobs/{job_b['id']}/resume-remaining").json()
        wait_for(mock_client, job_c["id"], lambda j: j["status"] == "COMPLETED")
    finally:
        adapter.fail_after_items = 0

    # 全部：族内 root = A，续跑任务 B、C 按创建顺序排列（Task6 两级归组）
    family = find_family(mock_client, job_a["id"], bucket="all")
    assert family is not None
    assert family["root"]["id"] == job_a["id"]
    assert [resume["id"] for resume in family["resumes"]] == [job_b["id"], job_c["id"]]
    assert family["root"]["positive_prompt_snapshot"]
    # 卡片展示所需字段都在 JobResponse 中（数量/Pipeline/来源/续跑关系）
    assert family["root"]["requested_count"] == 2
    assert family["root"]["workflow_snapshot"]["modules"][0]["module_id"] == "basic_generate"

    # 筛选：族内任一 Job 命中即保留整族
    assert find_family(mock_client, job_a["id"], bucket="failed") is not None
    assert find_family(mock_client, job_a["id"], bucket="completed") is not None  # C COMPLETED
    assert find_family(mock_client, job_a["id"], bucket="cancelled") is None
    assert find_family(mock_client, job_a["id"], bucket="active") is None
    assert find_family(mock_client, job_a["id"], source="resume") is not None
    assert find_family(mock_client, job_a["id"], source="web") is not None
    assert find_family(mock_client, job_a["id"], source="agent") is None

    # 非法筛选直接 4xx
    assert mock_client.get("/api/v1/history", params={"bucket": "weird"}).status_code == 422 or \
        mock_client.get("/api/v1/history", params={"bucket": "weird"}).status_code == 400


def test_history_can_resume_remaining_after_partial_failure(mock_client):
    """Task5 操作：符合状态时"继续剩余图片"（沿用既有 resume-remaining API，聚合仍归族）。"""
    adapter = mock_client.app.state.adapter
    adapter.fail_after_items = 1
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=2)}).json()
        wait_for(mock_client, job["id"], lambda j: j["status"] == "FAILED")
    finally:
        adapter.fail_after_items = 0

    detail = mock_client.get(f"/api/v1/jobs/{job['id']}").json()
    assert detail["status"] in ("FAILED", "CANCELLED", "INTERRUPTED")
    assert detail["completed_count"] < detail["requested_count"], "UI 依据此判断是否可续跑"

    resumed = mock_client.post(f"/api/v1/jobs/{job['id']}/resume-remaining").json()
    wait_for(mock_client, resumed["id"], lambda j: j["status"] == "COMPLETED")
    family = find_family(mock_client, job["id"], bucket="all")
    assert [item["id"] for item in family["resumes"]] == [resumed["id"]]


# ===== Task7 + Task9：派生图 → 工作台追溯根生成 Job + 完整执行身份 =====

def test_image_workbench_traces_root_generate_job(mock_client):
    job = mock_client.post("/api/v1/jobs", json={"snapshot": pipeline_snapshot(count=1)}).json()
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")
    images = gallery(mock_client, job["id"])
    original = next(image for image in images if image["kind"] == "original")
    upscaled = next(image for image in images if image["kind"] == "upscaled")

    # 高清图（派生图）→ 恢复的是根生成 Job 的配置，不是高清 process Job 的空 Prompt
    response = mock_client.get(f"/api/v1/images/{upscaled['id']}/workbench")
    assert response.status_code == 200
    payload = response.json()
    assert payload["snapshot"]["structured_prompt"]["style"] == "anime"
    assert payload["snapshot"]["structured_prompt"]["scene"] == "cafe"
    # Task9：workflow_modules 携带完整执行身份（含版本 + provider + 指纹字段）
    modules = payload["snapshot"]["workflow_modules"]
    assert [module["module_id"] for module in modules] == ["basic_generate", "upscale"]
    for module in modules:
        assert module["module_version"] == "v1"
        assert module["provider"] == "mock"
        assert module["binding_version"] == "v1"
    # Task7：Seed 返回根图 Seed；快照默认 random
    import_seed = original["seed"]
    assert payload["seed"] == import_seed
    assert payload["snapshot"]["seed_mode"] == "random"

    # 原图本身 → 同一套恢复
    response_original = mock_client.get(f"/api/v1/images/{original['id']}/workbench").json()
    assert response_original["seed"] == import_seed


def test_manual_upscale_workbench_returns_original_generation_config(mock_client):
    """图库手动高清（process Job）→ 从高清图打开工作台，恢复**来源原图**的生成配置。"""
    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1)}).json()
    wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")
    original = gallery(mock_client, job["id"])[0]

    process = mock_client.post("/api/v1/images/upscale", json={"image_ids": [original["id"]]}).json()
    assert process["job_kind"] == "process"
    wait_for(mock_client, process["id"], lambda j: j["status"] == "COMPLETED")
    upscaled = gallery(mock_client, process["id"])[0]

    payload = mock_client.get(f"/api/v1/images/{upscaled['id']}/workbench").json()
    assert payload["snapshot"]["structured_prompt"]["style"] == "anime", \
        "必须追溯根生成 Job（process Job 的快照是空 Prompt，绝不能返回它）"
    assert [module["module_id"] for module in payload["snapshot"]["workflow_modules"]] == ["basic_generate"]
    assert payload["seed"] == original["seed"]


def test_imported_image_has_no_generation_context(mock_client, png_bytes):
    """外部导入图：明确返回"没有可恢复的生成配置"，绝不伪造 Prompt。"""
    from app.services import image_service
    from app.storage.manager import StorageManager

    with mock_client.app.state.session_factory() as session:
        storage = StorageManager(mock_client.app.state.settings)
        imported = image_service.import_engine_output(
            session, storage, data=png_bytes, original_filename="x.png", source="import",
        )
        imported_id = imported.id

    response = mock_client.get(f"/api/v1/images/{imported_id}/workbench")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "IMAGE_NO_GENERATION_CONTEXT"
    assert response.json()["error"]["message"] == "没有可恢复的生成配置"


# ===== Task10：Image Provenance =====

def test_image_provenance_full_chain(mock_client, png_bytes):
    from app.services import image_service
    from app.storage.manager import StorageManager

    job = mock_client.post("/api/v1/jobs", json={"snapshot": pipeline_snapshot(count=1)}).json()
    wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")
    images = gallery(mock_client, job["id"])
    original = next(image for image in images if image["kind"] == "original")
    upscaled = next(image for image in images if image["kind"] == "upscaled")

    # 高清图：直接 job=生成 Job；stage_index=1 / module=upscale；seed=null
    provenance = mock_client.get(f"/api/v1/images/{upscaled['id']}/provenance").json()
    assert provenance["job_id"] == job["id"]
    assert provenance["job_item_id"]
    assert provenance["parent_image_id"] == original["id"]
    assert provenance["root_image_id"] == original["id"]
    assert provenance["stage_index"] == 1
    assert provenance["module_id"] == "upscale" and provenance["module_version"] == "v1"
    assert provenance["provider"] == "mock" and provenance["binding_version"] == "v1"
    assert provenance["stage_item_id"] and provenance["stage_id"]
    assert provenance["seed"] is None

    # 原图：stage_index=0 / module=basic_generate / seed 为真实 Seed
    origin_prov = mock_client.get(f"/api/v1/images/{original['id']}/provenance").json()
    assert origin_prov["stage_index"] == 0
    assert origin_prov["module_id"] == "basic_generate"
    assert origin_prov["parent_image_id"] is None
    assert origin_prov["root_image_id"] == original["id"]
    assert origin_prov["seed"] is not None

    # 外部导入图：无 job / 无 module，root 为自身
    with mock_client.app.state.session_factory() as session:
        storage = StorageManager(mock_client.app.state.settings)
        imported = image_service.import_engine_output(
            session, storage, data=png_bytes, original_filename="i.png", source="import",
        )
        imported_id = imported.id
    imported_prov = mock_client.get(f"/api/v1/images/{imported_id}/provenance").json()
    assert imported_prov["job_id"] is None
    assert imported_prov["module_id"] is None
    assert imported_prov["root_image_id"] == imported_id
    assert imported_prov["seed"] is None