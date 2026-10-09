"""Phase 7 Task0：真正 Stage-aware Resume（全离线 Mock，不依赖真实 ComfyUI）。

旧实现把整条 Pipeline 从 Stage 0 全部重跑；本文件锁死新语义：

1. basic → upscale：Stage2 全部失败 → resume 复用 Stage0 原图，只重跑 upscale；
2. img2img → upscale：Stage2 取消 → resume 绝不重跑 img2img（输入图不被二次消费）；
3. Stage1 部分完成 + Stage2 失败：已 COMPLETED 槽位不再续跑，剩余槽位复用其 Stage0 输出；
4. Stage0 取消：未完成槽位重新执行并分配新 Seed，已完成槽位复用原 Seed。

固定断言：
- 复用项 = COMPLETED + output_image_id 非空 + reused_from_stage_item_id 指向父 StageItem；
- 只有真正重新执行的 Stage 才重新分配 Seed（复用 Seed 原样保留）；
- 复用 Stage 的输出图绝不重复生成（引擎提交次数验证）；
- 链式图片流转：重跑 Stage 的输入 = 复用 Stage 的输出。
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import threading
import time

import pytest

from app.core.config import Settings, WorkflowConfig
from app.engine.base import EngineError
from app.main import create_app


def mock_settings(settings: Settings, **options) -> Settings:
    merged = {"worker_poll_interval_ms": 20, "engine_poll_ms": 20}
    merged.update(options)
    return dataclasses.replace(
        settings,
        workflow=WorkflowConfig(raw={"engine": {"provider": "mock", "options": merged}}),
    )


@pytest.fixture()
def mock_client(settings):
    from fastapi.testclient import TestClient

    app = create_app(mock_settings(settings))
    with TestClient(app) as test_client:
        yield test_client


def wait_for(client, job_id: str, predicate, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/api/v1/jobs/{job_id}").json()
        if predicate(last):
            return last
        time.sleep(0.05)
    raise AssertionError(f"等待任务状态超时: {json.dumps(last, ensure_ascii=False)[:500]}")


def wait_until(predicate, timeout: float = 10.0) -> None:
    """线程侧等待（用于等待异步 gate 触发；不访问 API）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("等待 gate 触发超时")


def make_snapshot(count: int = 1, **overrides) -> dict:
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


def pipeline_snapshot(count: int = 1, modules=("basic_generate", "upscale"), **overrides) -> dict:
    snapshot = make_snapshot(count=count, **overrides)
    snapshot["workflow_modules"] = [{"module_id": module_id} for module_id in modules]
    return snapshot


def import_one(client, name: str, data: bytes) -> dict:
    response = client.post("/api/v1/images/import", files=[("files", (name, data, "image/png"))])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["imported_count"] == 1, body
    return body["imported"][0]["image"]


def gallery(client, job_id: str) -> list[dict]:
    return client.get("/api/v1/images", params={"job_id": job_id, "limit": 200}).json()["items"]


def gate_submit(adapter, *, module_id: str, occurrence: int):
    """把指定模块的第 N 次提交挂起，直到返回的 release() 被测试线程调用。

    返回 (state, release)：state["entered"] 变为 True 表示 Worker 已停在 gate 上。
    """
    state = {"entered": False, "count": 0}
    release = threading.Event()
    original = adapter.submit_job

    async def gated(request):
        if request.binding.module_id == module_id:
            state["count"] += 1
            if state["count"] == occurrence:
                state["entered"] = True
                while not release.is_set():
                    await asyncio.sleep(0.02)
        return await original(request)

    adapter.submit_job = gated
    return state, release, original


def assert_reuse_trace(child: dict, child_stage_index: int, expected_parent_items: dict) -> None:
    """child[name] 的 stage[child_stage_index] 全部为复用项：溯源/产出/Seed 与父完全一致。"""
    stage = child["stages"][child_stage_index]
    assert stage["status"] == "COMPLETED"
    assert stage["completed_count"] == stage["total_count"]
    for item in stage["items"]:
        parent_item = expected_parent_items[item["item_index"]]
        assert item["status"] == "COMPLETED"
        assert item["output_image_id"] == parent_item["output_image_id"], "复用必须继承父产出"
        assert item["seed"] == parent_item["seed"], "复用项 Seed 原样保留（不重新分配）"
        assert item["reused_from_stage_item_id"] == parent_item["id"], "必须记录复用溯源"
        assert item["input_image_id"] == parent_item["input_image_id"]
        assert item["output_image_id"], "COMPLETED 复用项必须有真实产出"


# ===== 场景 1：basic → upscale，Stage2 全部失败 → 只重跑 upscale =====

def test_resume_basic_upscale_reuses_completed_stage0(mock_client):
    adapter = mock_client.app.state.adapter
    original_submit = adapter.submit_job

    async def fail_all_upscale(request):
        if request.binding.module_id == "upscale":
            raise EngineError("OUTPUT_MISSING", "mock: upscale 全部失败")
        return await original_submit(request)

    adapter.submit_job = fail_all_upscale
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": pipeline_snapshot(count=2)}).json()
        parent = wait_for(mock_client, job["id"], lambda j: j["status"] == "FAILED")
    finally:
        adapter.submit_job = original_submit

    assert parent["stages"][0]["status"] == "COMPLETED"
    assert parent["stages"][1]["status"] == "FAILED"
    parent_stage0 = {item["item_index"]: item for item in parent["stages"][0]["items"]}
    assert parent["completed_count"] == 0, "Stage2 全失败 → 无任何槽位完成"

    requests_before = len(adapter.submitted_requests)
    child = mock_client.post(f"/api/v1/jobs/{job['id']}/resume-remaining").json()
    assert child["requested_count"] == 2

    # 创建期即可断言：Stage0 整段复用（COMPLETED），Stage1 仍待执行（QUEUED）
    assert child["stages"][0]["status"] == "COMPLETED"
    assert child["stages"][1]["status"] == "QUEUED"
    assert_reuse_trace(child, 0, parent_stage0)

    final = wait_for(mock_client, child["id"], lambda j: j["status"] == "COMPLETED")
    assert final["completed_count"] == 2

    # 只重新执行了 upscale：绝无新的 basic_generate 提交
    resumed_requests = adapter.submitted_requests[requests_before:]
    assert [r.binding.module_id for r in resumed_requests] == ["upscale", "upscale"]

    # 链式流转：重跑 upscale 的输入 = 复用 Stage0 的输出
    for item in final["stages"][1]["items"]:
        assert item["input_image_id"] == parent_stage0[item["item_index"]]["output_image_id"]
        assert item["reused_from_stage_item_id"] is None, "真正重新执行的项不得有复用溯源"

    # 图库：子 Job 只新增 2 张高清（原图复用，不重复生成）
    images = gallery(mock_client, child["id"])
    assert len(images) == 2 and all(image["kind"] == "upscaled" for image in images)
    assert {image["parent_image_id"] for image in images} == {
        item["output_image_id"] for item in parent_stage0.values()
    }

    # 复用槽位的 JobItem Seed = 原 Stage0 Seed（只有真正重新执行的 Stage 才分配新 Seed）
    for item in final["items"]:
        assert item["seed"] == parent_stage0[item["item_index"]]["seed"] is not None


# ===== 场景 2：img2img → upscale，Stage2 取消 → 绝不重跑 img2img =====

def test_resume_img2img_upscale_cancel_never_reruns_img2img(mock_client, png_bytes):
    adapter = mock_client.app.state.adapter
    source = import_one(mock_client, "p7_cancel_src.png", png_bytes)
    state, release, original_submit = gate_submit(adapter, module_id="upscale", occurrence=1)
    try:
        snapshot = make_snapshot(
            count=2,
            input_images=[{"role": "source", "image_id": source["id"]}],
            workflow_modules=[{"module_id": "img2img"}, {"module_id": "upscale"}],
        )
        job = mock_client.post("/api/v1/jobs", json={"snapshot": snapshot}).json()
        wait_until(lambda: state["entered"], timeout=30)
        mock_client.post(f"/api/v1/jobs/{job['id']}/cancel")
        release.set()
        parent = wait_for(mock_client, job["id"], lambda j: j["status"] == "CANCELLED")
    finally:
        adapter.submit_job = original_submit

    assert parent["stages"][0]["status"] == "COMPLETED"
    assert parent["stages"][1]["status"] == "CANCELLED"
    assert parent["completed_count"] == 0, "Stage2 取消 → 槽位未走到终态"
    parent_stage0 = {item["item_index"]: item for item in parent["stages"][0]["items"]}
    assert all(item["seed"] is not None for item in parent_stage0.values())

    requests_before = len(adapter.submitted_requests)
    uploads_before = len(adapter.uploaded_inputs)
    child = mock_client.post(f"/api/v1/jobs/{job['id']}/resume-remaining").json()
    assert child["requested_count"] == 2
    assert child["workflow_snapshot"]["modules"][0]["module_id"] == "img2img"

    # 创建期：img2img 整段复用，Stage1 待执行
    assert_reuse_trace(child, 0, parent_stage0)
    assert child["stages"][1]["status"] == "QUEUED"

    final = wait_for(mock_client, child["id"], lambda j: j["status"] == "COMPLETED")

    # 绝不重跑 img2img：无 img2img 提交、无 img2img 输入图上传
    resumed_requests = adapter.submitted_requests[requests_before:]
    assert [r.binding.module_id for r in resumed_requests] == ["upscale", "upscale"]
    resumed_uploads = adapter.uploaded_inputs[uploads_before:]
    assert [image_id for _name, image_id in resumed_uploads] == [
        item["output_image_id"] for item in sorted(parent_stage0.values(), key=lambda i: i["item_index"])
    ], "upscale 的输入必须是被复用的 img2img 输出（输入图未被二次消费）"

    # 链式流转 + 复用 Seed
    for item in final["stages"][1]["items"]:
        assert item["input_image_id"] == parent_stage0[item["item_index"]]["output_image_id"]
    for item in final["items"]:
        assert item["seed"] == parent_stage0[item["item_index"]]["seed"]


# ===== 场景 3：Stage1 全部完成 + Stage2 部分失败 → 只续跑未完成槽位 =====

def test_resume_after_partial_stage2_failure_only_remaining_slot(mock_client):
    adapter = mock_client.app.state.adapter
    original_submit = adapter.submit_job
    state = {"upscale_count": 0}

    async def fail_second_upscale(request):
        if request.binding.module_id == "upscale":
            state["upscale_count"] += 1
            if state["upscale_count"] == 2:
                raise EngineError("OUTPUT_MISSING", "mock: 第 2 张高清失败")
        return await original_submit(request)

    adapter.submit_job = fail_second_upscale
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": pipeline_snapshot(count=2)}).json()
        parent = wait_for(mock_client, job["id"], lambda j: j["status"] == "FAILED")
    finally:
        adapter.submit_job = original_submit

    assert parent["completed_count"] == 1, "槽位 0 全链完成"
    assert parent["items"][0]["status"] == "COMPLETED"
    assert parent["items"][1]["status"] == "FAILED"
    parent_stage0 = {item["item_index"]: item for item in parent["stages"][0]["items"]}

    requests_before = len(adapter.submitted_requests)
    child = mock_client.post(f"/api/v1/jobs/{job['id']}/resume-remaining").json()
    assert child["requested_count"] == 1, "已 COMPLETED 槽位不再续跑"

    # 子 Job 的槽位 0 ↔ 父 Job 的槽位 1：Stage0 复用，Stage1 重跑
    expected_parent = {0: parent_stage0[1]}
    assert_reuse_trace(child, 0, expected_parent)
    assert child["stages"][1]["status"] == "QUEUED"

    final = wait_for(mock_client, child["id"], lambda j: j["status"] == "COMPLETED")
    resumed_requests = adapter.submitted_requests[requests_before:]
    assert [r.binding.module_id for r in resumed_requests] == ["upscale"]
    upsale_item = final["stages"][1]["items"][0]
    assert upsale_item["input_image_id"] == parent_stage0[1]["output_image_id"]
    assert final["items"][0]["seed"] == parent_stage0[1]["seed"]

    # 子 Job 只新增 1 张高清；原图复用（文件/记录都不重复）
    images = gallery(mock_client, child["id"])
    assert len(images) == 1 and images[0]["kind"] == "upscaled"
    assert images[0]["parent_image_id"] == parent_stage0[1]["output_image_id"]


# ===== 场景 4：Stage0 取消 → 未完成槽位重新执行（新 Seed），已完成槽位复用（原 Seed） =====

def test_resume_cancelled_stage0_reallocates_seed_only_for_rerun_slots(mock_client):
    adapter = mock_client.app.state.adapter
    state, release, original_submit = gate_submit(adapter, module_id="basic_generate", occurrence=2)
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": pipeline_snapshot(count=2)}).json()
        wait_until(lambda: state["entered"], timeout=30)
        mock_client.post(f"/api/v1/jobs/{job['id']}/cancel")
        release.set()
        parent = wait_for(mock_client, job["id"], lambda j: j["status"] == "CANCELLED")
    finally:
        adapter.submit_job = original_submit

    parent_stage0 = {item["item_index"]: item for item in parent["stages"][0]["items"]}
    assert parent_stage0[0]["status"] == "COMPLETED", "槽位 0 的原图在取消前已完成"
    assert parent_stage0[1]["status"] == "CANCELLED"
    assert parent_stage0[1]["seed"] is not None, "已启动过的槽位必须留有真实 Seed（用于对比）"

    requests_before = len(adapter.submitted_requests)
    child = mock_client.post(f"/api/v1/jobs/{job['id']}/resume-remaining").json()
    assert child["requested_count"] == 2

    child_stage0 = {item["item_index"]: item for item in child["stages"][0]["items"]}
    # 已完成的槽位复用（原 Seed）；取消的槽位重新执行（Seed 待 Worker 分配）
    assert child_stage0[0]["status"] == "COMPLETED"
    assert child_stage0[0]["reused_from_stage_item_id"] == parent_stage0[0]["id"]
    assert child_stage0[0]["seed"] == parent_stage0[0]["seed"]
    assert child_stage0[1]["status"] == "QUEUED"
    assert child_stage0[1]["reused_from_stage_item_id"] is None
    assert child_stage0[1]["seed"] is None
    assert child["stages"][0]["status"] == "QUEUED", "部分复用 → Stage 仍需执行未完成槽位"

    final = wait_for(mock_client, child["id"], lambda j: j["status"] == "COMPLETED")
    # 只有真正重新执行的 Stage 才重新分配 Seed：1 次 basic（槽位 1）+ 2 次 upscale
    resumed_requests = adapter.submitted_requests[requests_before:]
    assert [r.binding.module_id for r in resumed_requests] == [
        "basic_generate", "upscale", "upscale",
    ]
    final_stage0 = {item["item_index"]: item for item in final["stages"][0]["items"]}
    assert final_stage0[0]["seed"] == parent_stage0[0]["seed"], "复用槽位 Seed 绝不改变"
    assert final_stage0[1]["seed"] not in (None, parent_stage0[1]["seed"]), \
        "重新执行的 Stage 必须分配新 Seed（不得复用父 Job 的 Seed）"

    # 图片：子 Job = 1 张新原图（槽位 1）+ 2 张高清；复用原图不重复生成
    images = gallery(mock_client, child["id"])
    originals = [image for image in images if image["kind"] == "original"]
    assert len(originals) == 1
    assert {image["parent_image_id"] for image in images if image["kind"] == "upscaled"} == {
        parent_stage0[0]["output_image_id"], originals[0]["id"],
    }