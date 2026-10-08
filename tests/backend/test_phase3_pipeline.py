"""Phase 3 多阶段管线 + 高清放大回归（合同 §0.1 / §0.4 / §六~§十 / §二十五）。

全部离线可跑（Mock 引擎 + stub），无需真实 ComfyUI：
- 双阶段执行顺序：basic×N 全部完成 → 才进入 upscale×N（禁止交错）；
- Stage Gate：任一 StageItem FAILED → Stage FAILED → Job FAILED → 后续 Stage 不启动；
- Stage 2 暂停 / 取消 / 崩溃恢复（按 StageItem 核对）；
- 图库已有图片 → upscale-only process Job（同一 Worker / 同一 UpscaleModule）；
- parent_image_id / kind=upscaled / images/upscaled 存储；
- §0.1 Worker 代码级异常 → INTERRUPTED + 队列暂停；§十 ENGINE_TIMEOUT；§0.4 固定 Seed。
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


def wait_for(client, job_id, predicate, timeout=30.0):
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


def pipeline_snapshot(count=1, modules=("basic_generate", "upscale"), **overrides):
    """生成工作台"开启高清"后的快照：workflow_modules = 基础生成 + 高清放大（§五/§十五）。"""
    snapshot = make_snapshot(count=count, **overrides)
    snapshot["workflow_modules"] = [{"module_id": module_id} for module_id in modules]
    return snapshot


async def _noop_stop(timeout: float = 10.0) -> None:  # 跳过优雅收尾，制造"进程崩溃"现场
    return None


@pytest.fixture()
def mock_client(settings):
    from fastapi.testclient import TestClient

    app = create_app(mock_settings(settings))
    with TestClient(app) as test_client:
        yield test_client


def gallery(client, job_id: str) -> list[dict]:
    response = client.get("/api/v1/images", params={"job_id": job_id, "limit": 200}).json()
    return response["items"]


# ===== §二十五(1)：3 张 basic only =====

def test_basic_only_single_stage(mock_client):
    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=3)}).json()
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")
    stages = final["stages"]
    assert len(stages) == 1
    assert stages[0]["module_id"] == "basic_generate"
    assert stages[0]["status"] == "COMPLETED"
    assert (stages[0]["total_count"], stages[0]["completed_count"]) == (3, 3)
    assert all(item["status"] == "COMPLETED" for item in final["items"])
    images = gallery(mock_client, job["id"])
    assert len(images) == 3 and all(image["kind"] == "original" for image in images)


# ===== §二十五(2)(3)(10)：3 张 basic + upscale（严格顺序 + 父子关系） =====

def test_basic_then_upscale_strict_order_and_parents(mock_client):
    adapter = mock_client.app.state.adapter
    job = mock_client.post("/api/v1/jobs", json={"snapshot": pipeline_snapshot(count=3)}).json()
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED", timeout=60)

    # 执行顺序严格为 basic1 basic2 basic3 → upscale1 upscale2 upscale3（禁止交错）
    modules_seq = [request.binding.module_id for request in adapter.submitted_requests]
    assert modules_seq == ["basic_generate"] * 3 + ["upscale"] * 3
    stage_seq = [request.metadata.get("stage_index") for request in adapter.submitted_requests]
    assert stage_seq == [0, 0, 0, 1, 1, 1]
    # upscale 的输入是上一 Stage 同槽位的输出（生成 N 张全部完成才开始高清）
    first_upscale = next(r for r in adapter.submitted_requests if r.binding.module_id == "upscale")
    assert first_upscale.parameters.get("input_image"), "upscale 必须注入已上传的输入图片引用"

    stages = final["stages"]
    assert [stage["module_id"] for stage in stages] == ["basic_generate", "upscale"]
    assert all(stage["status"] == "COMPLETED" for stage in stages)
    stage0_items = {item["item_index"]: item for item in stages[0]["items"]}
    for item in stages[1]["items"]:
        assert item["input_image_id"] == stage0_items[item["item_index"]]["output_image_id"], \
            "Stage 2 的输入必须是同槽位 Stage 1 的输出"
        assert item["output_image_id"], "Stage 2 完成必须有高清输出"

    # 每个槽位的最终输出 = 高清图（JobItem.image_id 指向 upscaled）
    for stage1_item in stages[1]["items"]:
        job_item = next(i for i in final["items"] if i["id"] == stage1_item["job_item_id"])
        assert job_item["image_id"] == stage1_item["output_image_id"]
        assert job_item["status"] == "COMPLETED"

    # 图库：3 原图 + 3 高清；kind / parent_image_id / 存储目录正确
    images = gallery(mock_client, job["id"])
    assert len(images) == 6
    originals = {image["id"]: image for image in images if image["kind"] == "original"}
    upscaled = [image for image in images if image["kind"] == "upscaled"]
    assert len(originals) == 3 and len(upscaled) == 3
    for image in upscaled:
        assert image["file_path"].startswith("images/upscaled/")
        assert image["parent_image_id"] in originals
    for image in originals.values():
        assert image["file_path"].startswith("images/originals/")

    # 父子关系 API（§十九）
    one = upscaled[0]
    versions = mock_client.get(f"/api/v1/images/{one['id']}/versions").json()
    assert versions["parent"]["id"] == one["parent_image_id"]
    parent_versions = mock_client.get(f"/api/v1/images/{one['parent_image_id']}/versions").json()
    assert parent_versions["parent"] is None
    assert [child["id"] for child in parent_versions["children"]] == [one["id"]]


# ===== §二十五(4)：Stage 1 任一失败 → Stage 2 不启动 =====

def test_stage_gate_stage2_not_started_when_stage1_fails(mock_client):
    adapter = mock_client.app.state.adapter
    adapter.fail_after_items = 2  # 第 3 次提交开始失败
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": pipeline_snapshot(count=3)}).json()
        final = wait_for(mock_client, job["id"], lambda j: j["status"] == "FAILED", timeout=60)
    finally:
        adapter.fail_after_items = 0

    assert [r.binding.module_id for r in adapter.submitted_requests] == ["basic_generate"] * 3, \
        "Stage 0 FAILED 后绝不允许启动 Stage 1"
    stages = final["stages"]
    assert stages[0]["status"] == "FAILED"
    assert stages[1]["status"] == "QUEUED" and stages[1]["completed_count"] == 0
    statuses = [item["status"] for item in final["items"]]
    # 前两张原图已生成（image_id 保留），但最终逻辑结果（高清）未产出 → CANCELLED，不悬空 RUNNING
    assert statuses == ["CANCELLED", "CANCELLED", "FAILED"]
    assert all(item["image_id"] for item in final["items"][:2]), "已完成的原图仍作为槽位当前输出保留"
    images = gallery(mock_client, job["id"])
    assert len(images) == 2 and all(image["kind"] == "original" for image in images), \
        "已成功生成的原图必须保留"


# ===== §二十五(5)：Stage 2 第 2 张失败 → 原图全部保留 =====

def test_stage2_partial_failure_keeps_all_originals(mock_client):
    from app.engine.base import EngineError

    adapter = mock_client.app.state.adapter
    original_submit = adapter.submit_job
    state = {"upscale_count": 0}

    async def failing_second_upscale(request):
        if request.binding.module_id == "upscale":
            state["upscale_count"] += 1
            if state["upscale_count"] == 2:
                raise EngineError("OUTPUT_MISSING", "mock: 第 2 张高清失败")
        return await original_submit(request)

    adapter.submit_job = failing_second_upscale
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": pipeline_snapshot(count=2)}).json()
        final = wait_for(mock_client, job["id"], lambda j: j["status"] == "FAILED", timeout=60)
    finally:
        adapter.submit_job = original_submit

    stages = final["stages"]
    assert stages[0]["status"] == "COMPLETED"
    assert stages[1]["status"] == "FAILED"
    assert final["items"][1]["status"] == "FAILED"
    assert final["items"][0]["status"] == "COMPLETED"
    images = gallery(mock_client, job["id"])
    kept_originals = [image for image in images if image["kind"] == "original"]
    kept_upscaled = [image for image in images if image["kind"] == "upscaled"]
    assert len(kept_originals) == 2, "高清失败不得影响原图保留"
    assert len(kept_upscaled) == 1, "失败前已完成的高清同样保留"
    assert kept_upscaled[0]["parent_image_id"] in {image["id"] for image in kept_originals}


# ===== §二十五(6)：Stage 2 暂停 / 继续 =====

def test_stage2_pause_and_resume(mock_client):
    adapter = mock_client.app.state.adapter
    adapter.delay_per_item_ms = 150
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": pipeline_snapshot(count=3)}).json()
        wait_for(mock_client, job["id"],
                 lambda j: len(j["stages"]) > 1 and j["stages"][1]["completed_count"] >= 1,
                 timeout=60)
        mock_client.post(f"/api/v1/jobs/{job['id']}/pause")
        paused = wait_for(mock_client, job["id"], lambda j: j["status"] == "PAUSED", timeout=30)
    finally:
        adapter.delay_per_item_ms = 50

    stage1 = paused["stages"][1]
    assert 1 <= stage1["completed_count"] < 3, "暂停发生在 StageItem 边界（当前高清完成后）"
    assert stage1["status"] != "COMPLETED"
    running_items = [item for stage in paused["stages"] for item in stage["items"]
                     if item["status"] == "RUNNING"]
    assert running_items == [], "暂停后不应有 RUNNING StageItem"
    checkpoint_ids = [item["id"] for item in stage1["items"] if item["status"] == "COMPLETED"]

    mock_client.post(f"/api/v1/jobs/{job['id']}/resume")
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED", timeout=60)
    assert final["completed_count"] == 3
    assert all(stage["status"] == "COMPLETED" for stage in final["stages"])
    for item in final["stages"][1]["items"]:
        if item["id"] in checkpoint_ids:
            assert item["status"] == "COMPLETED", "已完成的 StageItem 绝不重跑"
    assert len(gallery(mock_client, job["id"])) == 6


# ===== §二十五(7)：Stage 2 取消（已完成的原图/高清全部保留） =====

def test_stage2_cancel_keeps_generated(mock_client):
    adapter = mock_client.app.state.adapter
    adapter.delay_per_item_ms = 150
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": pipeline_snapshot(count=3)}).json()
        wait_for(mock_client, job["id"],
                 lambda j: len(j["stages"]) > 1 and j["stages"][1]["completed_count"] >= 1,
                 timeout=60)
        mock_client.post(f"/api/v1/jobs/{job['id']}/cancel")
        final = wait_for(mock_client, job["id"], lambda j: j["status"] == "CANCELLED", timeout=30)
    finally:
        adapter.delay_per_item_ms = 50

    assert final["stages"][0]["status"] == "COMPLETED"
    images = gallery(mock_client, job["id"])
    originals = [image for image in images if image["kind"] == "original"]
    upscaled = [image for image in images if image["kind"] == "upscaled"]
    assert len(originals) == 3, "取消不得丢弃已生成的原图"
    assert len(upscaled) == final["completed_count"] >= 1, "已生成的高清保留，未完成的取消"
    assert final["stages"][1]["status"] == "CANCELLED"


# ===== §二十五(8)：Stage 2 崩溃恢复（按 StageItem 核对） =====

def test_stage2_crash_recovery(settings, monkeypatch):
    from fastapi.testclient import TestClient

    from app.engine.base import EngineJobStatus, EngineOutputFile
    from app.engine.mock import PNG_FIXTURE, MockEngineAdapter
    from app.models import JobEvent
    from sqlalchemy import select

    app = create_app(mock_settings(settings))
    with TestClient(app) as client:
        client.app.state.adapter.delay_per_item_ms = 40
        job = client.post("/api/v1/jobs", json={"snapshot": pipeline_snapshot(count=1)}).json()
        job_id = job["id"]
        # 等到 Stage 1 的 StageItem 已经在引擎侧运行（engine_job_id 已记录）再"崩溃"
        wait_for(client, job_id,
                 lambda j: len(j["stages"]) > 1 and j["stages"][1]["items"][0]["engine_job_id"],
                 timeout=60)
        client.app.state.adapter.delay_per_item_ms = 15_000  # 卡住轮询
        client.app.state.worker.stop = _noop_stop
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
        detail = wait_for(client2, job_id, lambda j: j["status"] == "COMPLETED", timeout=30)
        assert all(stage["status"] == "COMPLETED" for stage in detail["stages"]), \
            "恢复不得重新跑已经完成的 Stage"
        assert detail["completed_count"] == 1
        images = gallery(client2, job_id)
        original = next(image for image in images if image["kind"] == "original")
        upscaled = next(image for image in images if image["kind"] == "upscaled")
        assert upscaled["parent_image_id"] == original["id"], "恢复的高清必须正确挂回原图"
        with client2.app.state.session_factory() as session:
            types = [event.event_type for event in session.execute(
                select(JobEvent).where(JobEvent.job_id == job_id)
            ).scalars()]
        assert "JOB_RECOVERED_COMPLETED" in types


# ===== §二十五(9)(11)：图库 N 张 → upscale-only process Job =====

def _seed_gallery_images(client, count: int, png_bytes: bytes) -> list[str]:
    from app.services import image_service
    from app.storage.manager import StorageManager

    with client.app.state.session_factory() as session:
        storage = StorageManager(client.app.state.settings)
        ids = []
        for index in range(count):
            image = image_service.import_engine_output(
                session, storage, data=png_bytes, original_filename=f"seed{index}.png", source="import",
            )
            ids.append(image.id)
        return ids


def test_gallery_upscale_creates_process_job(mock_client, png_bytes):
    adapter = mock_client.app.state.adapter
    source_ids = _seed_gallery_images(mock_client, 3, png_bytes)

    response = mock_client.post("/api/v1/images/upscale", json={"image_ids": source_ids})
    assert response.status_code == 201
    job = response.json()
    assert job["job_kind"] == "process"
    assert [stage["module_id"] for stage in job["stages"]] == ["upscale"], "不得重跑基础生成"
    assert job["requested_count"] == 3

    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED", timeout=60)
    assert [r.binding.module_id for r in adapter.submitted_requests] == ["upscale"] * 3
    stage_items = final["stages"][0]["items"]
    assert [item["input_image_id"] for item in stage_items] == source_ids, \
        "StageItem.input_image_id 必须是对应的已有图片（不得另存为新原图）"

    # 高清图 parent 正确；源图片不会被复制成新的"原图"
    images = gallery(mock_client, job["id"])
    assert len(images) == 3 and all(image["kind"] == "upscaled" for image in images)
    parents = {image["parent_image_id"] for image in images}
    assert parents == set(source_ids)
    for image in images:
        assert image["file_path"].startswith("images/upscaled/")


# ===== §0.1：Worker 代码级异常 → 当前 Job INTERRUPTED + 队列暂停 + 不启动第二 Job =====

def test_worker_internal_error_pauses_queue(mock_client):
    adapter = mock_client.app.state.adapter
    original_submit = adapter.submit_job
    armed = {"once": True}

    async def exploding_submit(request):
        if armed["once"]:
            armed["once"] = False
            raise RuntimeError("模拟 Worker 代码级异常")
        return await original_submit(request)

    adapter.submit_job = exploding_submit
    try:
        job_a = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot()}).json()
        job_b = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot()}).json()
        final_a = wait_for(mock_client, job_a["id"], lambda j: j["status"] == "INTERRUPTED", timeout=30)
        assert final_a["error_type"] == "WORKER_INTERNAL_ERROR"
        assert final_a["stages"][0]["status"] == "INTERRUPTED"
        assert final_a["items"][0]["status"] == "INTERRUPTED"

        queue = mock_client.get("/api/v1/queue").json()
        assert queue["worker"]["queue_paused"] is True
        time.sleep(0.6)
        assert mock_client.get(f"/api/v1/jobs/{job_b['id']}").json()["status"] == "QUEUED", \
            "队列暂停后绝不允许启动第二个 Job"
    finally:
        adapter.submit_job = original_submit

    # 用户恢复队列后，后续 Job 正常执行
    mock_client.post("/api/v1/queue/resume")
    wait_for(mock_client, job_b["id"], lambda j: j["status"] == "COMPLETED", timeout=30)


# ===== §二十五(12)：workflow_hash 不一致 → 系统性拒绝（队列暂停） =====

def test_workflow_hash_mismatch_fails_systemically(mock_client):
    from app.engine.base import EngineError

    adapter = mock_client.app.state.adapter
    original_submit = adapter.submit_job

    async def tampered_submit(request):
        raise EngineError("WORKFLOW_HASH_MISMATCH", "binding 已被改动（immutable 违约）")

    adapter.submit_job = tampered_submit
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot()}).json()
        final = wait_for(mock_client, job["id"], lambda j: j["status"] == "FAILED", timeout=30)
        assert final["error_type"] == "WORKFLOW_HASH_MISMATCH"
        assert mock_client.get("/api/v1/queue").json()["worker"]["queue_paused"] is True
    finally:
        adapter.submit_job = original_submit
        mock_client.post("/api/v1/queue/resume")


# ===== §十：StageItem 执行总超时 → ENGINE_TIMEOUT（不自动重试） =====

def test_stage_item_execution_timeout(mock_client):
    from app.services import job_service

    adapter = mock_client.app.state.adapter
    adapter.delay_per_item_ms = 10_000  # 每轮询 10 秒 → 永远不会在超时前完成
    try:
        # 服务层直建（携带 stage_configs），确保 Worker 领取前超时配置已固化
        with mock_client.app.state.session_factory() as session:
            modules = [{"module_id": "basic_generate", "module_version": "v1",
                        "provider": "mock", "binding_version": "v1", "workflow_hash": None}]
            job, _ = job_service.create_job(
                session, source="web", snapshot=make_snapshot(),
                workflow_modules=modules, stage_configs=[{"execution_timeout": 0.2}],
            )
            job_id = job.id
        final = wait_for(mock_client, job_id, lambda j: j["status"] == "FAILED", timeout=40)
        failed = final["items"][0]
        assert failed["error_type"] == "ENGINE_TIMEOUT"
        assert failed["retry_count"] == 0, "ENGINE_TIMEOUT 不自动重试"
        assert final["stages"][0]["status"] == "FAILED"
        assert mock_client.get("/api/v1/queue").json()["worker"]["queue_paused"] is False
    finally:
        adapter.delay_per_item_ms = 50


# ===== §二十五(15)：Recipe 开启高清后保存 / 恢复一致 =====

def test_recipe_roundtrip_with_upscale_module(mock_client):
    from app.services import recipe_service

    with mock_client.app.state.session_factory() as session:
        recipe = recipe_service.create_recipe(
            session,
            name="高清配方",
            prompt_mode="structured",
            structured={"style": "anime"},
            generation_settings={"width": 512, "height": 768, "default_count": 2},
            workflow_modules=[{"module_id": "basic_generate"}, {"module_id": "upscale"}],
        )
        version = recipe_service.get_current_version(session, recipe)
        modules = json.loads(version.workflow_snapshot_json)["modules"]
    assert [module["module_id"] for module in modules] == ["basic_generate", "upscale"], \
        "保存配方必须完整保留高清开关（basic_generate + upscale）"

    # 用恢复出的 workflow_modules 创建 Job：Pipeline 必须两次物化
    snapshot = make_snapshot(count=1)
    snapshot["workflow_modules"] = modules
    job = mock_client.post("/api/v1/jobs", json={"snapshot": snapshot}).json()
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED", timeout=60)
    assert [stage["module_id"] for stage in final["stages"]] == ["basic_generate", "upscale"]