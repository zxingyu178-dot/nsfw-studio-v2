"""Phase 2.1 执行稳定性回归套件（规范 §一/§二/§三/§四/§五/§六/§八/§九）。

覆盖缺陷：
- 无图片却 COMPLETED（OUTPUT_MISSING / 取输出异常 / 导入异常 / 导入空结果）
- 引擎掉线后永久 RUNNING（mock 掉线 → 有限时间内 FAILED + 队列暂停）
- QueueWorker 不得包含模块知识（源码 token 断言）+ 真实 BasicGenerateModule 被执行
- Workflow Snapshot 同步真实执行 + Resume 使用新随机 Seed
- 队列执行顺序唯一事实源 = queue_position（next Job 拖拽后必须尊重拖拽顺序）
- Job API 严格校验（宽高/数量/Seed 范围与 Prompt 长度上限）
- Cancel 请求失败的安全降级
"""
from __future__ import annotations

import asyncio
import dataclasses
import io
import json
import time
import tokenize
from pathlib import Path

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


@pytest.fixture()
def mock_client(settings):
    from fastapi.testclient import TestClient

    app = create_app(mock_settings(settings))
    with TestClient(app) as test_client:
        yield test_client


def gallery_total(client, job_id: str) -> int:
    return client.get("/api/v1/images", params={"job_id": job_id}).json()["total"]


# ===== §一：无图片不得 COMPLETED =====

def test_no_outputs_never_completed(mock_client):
    """history 成功但无输出 → OUTPUT_MISSING，不得 COMPLETED / image_id=null。"""
    adapter = mock_client.app.state.adapter
    adapter.no_outputs = True
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot()}).json()
        final = wait_for(mock_client, job["id"], lambda j: j["status"] == "FAILED")
        item = final["items"][0]
        assert item["status"] == "FAILED" and item["error_type"] == "OUTPUT_MISSING"
        assert item["image_id"] is None
        assert final["completed_count"] == 0
        assert gallery_total(mock_client, job["id"]) == 0
    finally:
        adapter.no_outputs = False


def test_outputs_error_classified_and_failed(mock_client):
    """取输出异常 → 正确分类（ENGINE_NETWORK），Item/Job FAILED，不得 COMPLETED。"""
    adapter = mock_client.app.state.adapter
    adapter.outputs_error = "ENGINE_NETWORK"
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot()}).json()
        final = wait_for(mock_client, job["id"], lambda j: j["status"] == "FAILED")
        item = final["items"][0]
        assert item["error_type"] == "ENGINE_NETWORK" and item["image_id"] is None
        assert final["completed_count"] == 0
    finally:
        adapter.outputs_error = None


def test_import_raises_storage_error_not_completed(mock_client):
    """output_importer 抛异常 → STORAGE_ERROR，不得 COMPLETED。"""
    worker = mock_client.app.state.worker
    original = worker._output_importer

    def boom(job, item, outputs):
        raise RuntimeError("模拟磁盘写入失败")

    worker._output_importer = boom
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot()}).json()
        final = wait_for(mock_client, job["id"], lambda j: j["status"] == "FAILED")
        item = final["items"][0]
        assert item["status"] == "FAILED" and item["error_type"] == "STORAGE_ERROR"
        assert item["image_id"] is None
        assert final["completed_count"] == 0
        assert gallery_total(mock_client, job["id"]) == 0
    finally:
        worker._output_importer = original


def test_import_empty_result_storage_error(mock_client):
    """导入返回空 image_ids → STORAGE_ERROR（未真正导入 Studio Image）。"""
    worker = mock_client.app.state.worker
    original = worker._output_importer
    worker._output_importer = lambda job, item, outputs: []
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot()}).json()
        final = wait_for(mock_client, job["id"], lambda j: j["status"] == "FAILED")
        item = final["items"][0]
        assert item["error_type"] == "STORAGE_ERROR" and item["image_id"] is None
        assert final["completed_count"] == 0
    finally:
        worker._output_importer = original


def test_success_imports_image_and_item_has_image_id(mock_client):
    """正常路径回归：成功导入后 Item.image_id 非空（禁止 COMPLETED + image_id=null）。"""
    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=2)}).json()
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")
    assert final["completed_count"] == 2
    for item in final["items"]:
        assert item["status"] == "COMPLETED" and item["image_id"], "COMPLETED 必须伴随 image_id"
    assert gallery_total(mock_client, job["id"]) == 2


# ===== §二：引擎掉线不得永久 RUNNING =====

def test_engine_offline_after_submit_fails_not_running(mock_client):
    """任务已 submit → Engine 突然不可达 → 有限时间内 FAILED + 队列暂停（不得永久 RUNNING）。"""
    adapter = mock_client.app.state.adapter
    adapter.delay_per_item_ms = 120
    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=3)}).json()
    try:
        wait_for(mock_client, job["id"], lambda j: j["status"] == "RUNNING", timeout=10)
        adapter.set_offline(True)
        final = wait_for(mock_client, job["id"], lambda j: j["status"] == "FAILED", timeout=20)
        assert final["error_type"] == "ENGINE_OFFLINE"
        queue = mock_client.get("/api/v1/queue").json()
        assert queue["worker"]["queue_paused"] is True
    finally:
        adapter.set_offline(False)
        adapter.delay_per_item_ms = 50
        mock_client.post("/api/v1/queue/resume")


# ===== §三：QueueWorker 不得包含模块知识 / 真实模块被执行 =====

def _code_without_comments(source: str) -> str:
    """去掉注释与字符串字面量（tokenize），只留可执行代码标识。"""
    output: list[str] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        output.append(token.string)
    return " ".join(output)


def test_queue_worker_has_no_module_knowledge():
    """QueueWorker 不得硬编码 basic_generate 的参数结构（§三 职责解耦）。"""
    from app.workers import queue_worker

    code = _code_without_comments(Path(queue_worker.__file__).read_text(encoding="utf-8"))
    for forbidden in ("basic_generate", "positive_prompt", "negative_prompt", "comfyui"):
        assert forbidden not in code, f"QueueWorker 代码不得出现 {forbidden}"


def test_job_executes_real_module_and_records_snapshot(mock_client):
    """§四：Job 的 workflow_snapshot.modules 必须同步真实执行模块；执行经 PipelineExecutor。"""
    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot()}).json()
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")
    modules = final["workflow_snapshot"]["modules"]
    assert modules, "实际执行了 basic_generate，workflow_snapshot.modules 不能为空"
    assert modules[0]["module_id"] == "basic_generate"
    assert modules[0]["module_version"] == "v1"
    assert modules[0]["provider"] == "mock"
    assert final["module_id"] == "basic_generate"


def test_basic_generate_module_contract():
    """BasicGenerateModule：能力声明 / 标准输入映射 / 范围校验（纯模块单测）。"""
    from app.engine.base import EngineError
    from app.workflows import BasicGenerateModule, JobRequestContext, WorkflowInput

    module = BasicGenerateModule()
    caps = module.capabilities()
    assert caps.module_id == "basic_generate" and caps.module_version == "v1"
    assert {spec.name for spec in caps.parameters} == {
        "positive_prompt", "negative_prompt", "width", "height", "seed",
    }

    context = JobRequestContext(
        positive_prompt="a cat", negative_prompt="blurry",
        generation_settings={"width": 640, "height": 960}, seed=42,
    )
    request = module.build_engine_request(context)
    assert request.job_type == "basic_generate"
    assert request.parameters == {
        "positive_prompt": "a cat", "negative_prompt": "blurry",
        "width": 640, "height": 960, "seed": 42,
    }

    bad = module.validate_input(WorkflowInput(values={"width": 10, "height": 10, "seed": -1}))
    assert not bad.ok and len(bad.errors) == 3
    with pytest.raises(EngineError) as excinfo:
        module.build_engine_request(dataclasses.replace(context, seed=-5))
    assert excinfo.value.error_type == "WORKFLOW_ERROR"


def test_pipeline_executor_full_path_with_mock_engine():
    """PipelineExecutor.execute：模块完整执行（提交→等待→输出引用）走通。"""
    from app.engine.mock import MockEngineAdapter
    from app.models import Job
    from app.workflows import PipelineExecutor

    job = Job(
        id="job_test_pipeline",
        positive_prompt_snapshot="a cat",
        negative_prompt_snapshot="",
        generation_settings_json=json.dumps({"width": 512, "height": 512}),
        workflow_snapshot_json=json.dumps({"modules": [{"module_id": "basic_generate", "module_version": "v1"}]}),
    )
    adapter = MockEngineAdapter({"delay_per_item_ms": 1})
    output = asyncio.run(PipelineExecutor().execute(job, seed=7, adapter=adapter))
    assert output.metadata["module_id"] == "basic_generate"
    assert output.artifacts and all(name.endswith(".png") for name in output.artifacts.values())


def test_registry_rejects_unknown_module():
    from app.engine.base import EngineError
    from app.workflows import default_registry

    with pytest.raises(EngineError) as excinfo:
        default_registry().get("upscale", "v1")
    assert excinfo.value.error_type == "WORKFLOW_ERROR"
    assert default_registry().has("basic_generate", "v1")


# ===== §五：Resume 必须使用新随机 Seed =====

def test_resume_remaining_uses_new_random_seed(mock_client):
    """fixed-seed Parent → 取消 → Resume Child：Child 必须 random，不得复用 Parent Seed。"""
    body = {"snapshot": make_snapshot(count=4, seed_mode="fixed", seed=1000)}
    job = mock_client.post("/api/v1/jobs", json=body).json()
    wait_for(mock_client, job["id"], lambda j: j["status"] == "RUNNING" and j["completed_count"] >= 1)
    mock_client.post(f"/api/v1/jobs/{job['id']}/cancel")
    parent = wait_for(mock_client, job["id"], lambda j: j["status"] == "CANCELLED")
    parent_completed = [i for i in parent["items"] if i["status"] == "COMPLETED"]
    assert parent_completed, "取消前应至少完成一张"

    child = mock_client.post(f"/api/v1/jobs/{job['id']}/resume-remaining").json()
    snapshot = child["workbench_snapshot"]
    assert snapshot["seed_mode"] == "random" and snapshot["seed"] is None
    assert snapshot["count"] == parent["requested_count"] - len(parent_completed)
    assert child["generation_settings"]["seed_mode"] == "random"
    assert child["generation_settings"]["seed"] is None
    assert child["resume_of_job_id"] == job["id"]

    # 原 Job 快照永不修改
    parent_after = mock_client.get(f"/api/v1/jobs/{job['id']}").json()
    assert parent_after["workbench_snapshot"]["seed_mode"] == "fixed"
    assert parent_after["workbench_snapshot"]["seed"] == 1000

    # 子 Job 实际执行使用新随机 Seed（不得出现 1000+index）
    child_final = wait_for(mock_client, child["id"], lambda j: j["status"] == "COMPLETED")
    child_seeds = {item["seed"] for item in child_final["items"]}
    assert len(child_seeds) == child["requested_count"]
    assert not (child_seeds & {1000 + index for index in range(parent["requested_count"])}), \
        "续跑不得复用父 Job 的固定 Seed"


# ===== §六：queue_position 是唯一执行顺序事实源 =====

def test_next_job_reorder_respected_by_queue_and_execution(mock_client):
    """创建 next Job → 拖到普通 Job 后面 → GET /queue 与实际执行顺序都必须遵守拖拽顺序。"""
    adapter = mock_client.app.state.adapter
    adapter.delay_per_item_ms = 100
    running = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=2)}).json()
    try:
        wait_for(mock_client, running["id"], lambda j: j["status"] == "RUNNING", timeout=10)
        normal = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot()}).json()
        priority = mock_client.post(
            "/api/v1/jobs", json={"snapshot": make_snapshot(), "queue_mode": "next"}
        ).json()

        queue = mock_client.get("/api/v1/queue").json()
        assert [j["id"] for j in queue["queued"]] == [priority["id"], normal["id"]], \
            "next Job 应先插到等待队列最前"

        # 用户把 next Job 拖到普通 Job 后面
        reordered = mock_client.post(
            "/api/v1/queue/reorder", json={"ordered_job_ids": [normal["id"], priority["id"]]}
        ).json()
        assert [j["id"] for j in reordered["queued"]] == [normal["id"], priority["id"]]
        queue_after = mock_client.get("/api/v1/queue").json()
        assert [j["id"] for j in queue_after["queued"]] == [normal["id"], priority["id"]], \
            "priority=1 不得越过拖拽后的 queue_position"

        # 实际执行顺序：running 完成后必须先是 normal
        wait_for(mock_client, running["id"], lambda j: j["status"] == "COMPLETED", timeout=30)
        deadline = time.monotonic() + 20
        executed_first = None
        while time.monotonic() < deadline:
            state = mock_client.get("/api/v1/queue").json()
            if state["running"] is not None:
                executed_first = state["running"]["id"]
                break
            time.sleep(0.05)
        assert executed_first == normal["id"], "实际执行顺序必须严格遵守 queue_position"
    finally:
        adapter.delay_per_item_ms = 50


# ===== §八：Job API 严格校验 =====

@pytest.mark.parametrize("overrides", [
    {"width": 32}, {"width": 5000}, {"height": 32}, {"height": 5000},
    {"count": 0}, {"count": 65}, {"seed_mode": "fixed", "seed": -5},
])
def test_job_create_rejects_out_of_range(mock_client, overrides):
    response = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(**overrides)})
    assert response.status_code == 422, overrides
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_job_create_rejects_overlong_prompt(mock_client):
    """结构化字段 > 2000 字符 / Negative > 8000 字符 → 400 PROMPT_TOO_LONG（§八）。"""
    long_field = mock_client.post(
        "/api/v1/jobs",
        json={"snapshot": make_snapshot(structured_prompt={"style": "x" * 2500})},
    )
    assert long_field.status_code == 400
    assert long_field.json()["error"]["code"] == "PROMPT_TOO_LONG"

    long_negative = mock_client.post(
        "/api/v1/jobs",
        json={"snapshot": make_snapshot(negative_prompt="y" * 9000)},
    )
    assert long_negative.status_code == 400
    assert long_negative.json()["error"]["code"] == "PROMPT_TOO_LONG"


# ===== §九：Cancel 异常保护 =====

def test_cancel_request_failure_still_cancels_safely(mock_client):
    """取消请求失败（网络异常）→ 当前 Item 可完成，完成后 Job=CANCELLED（不异常退出/不 COMPLETED）。"""
    from app.engine.base import EngineError

    adapter = mock_client.app.state.adapter
    adapter.delay_per_item_ms = 80
    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=3)}).json()
    wait_for(mock_client, job["id"], lambda j: j["status"] == "RUNNING")

    async def failing_cancel(engine_job_id):
        raise EngineError("ENGINE_NETWORK", "mock cancel network failure", transient=True)

    adapter.cancel_job = failing_cancel
    try:
        mock_client.post(f"/api/v1/jobs/{job['id']}/cancel")
        final = wait_for(mock_client, job["id"], lambda j: j["status"] == "CANCELLED", timeout=30)
        assert final["completed_count"] >= 1, "取消请求失败时允许当前 Item 完成"
        time.sleep(0.5)
        assert mock_client.get(f"/api/v1/jobs/{job['id']}").json()["status"] == "CANCELLED"
    finally:
        adapter.delay_per_item_ms = 50