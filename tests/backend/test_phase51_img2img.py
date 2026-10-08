"""Phase 5.1 Gate C 成功路径测试：Img2ImgModule 正式接入（全离线 Mock）。

覆盖：
- img2img 作为 Stage0（图片生成模式 Primary Module）→ kind=processed / parent=输入图 / Seed 记录；
- Pipeline 链式（img2img → upscale）Stage Gate 正常；
- denoise 经 config 单链进入 JobStage.config_json 与引擎请求；
- 缺输入图 / 非法 denoise 在 Job 创建期拒绝；
- Resume 剩余：继承 img2img 身份 + config，并重新冻结输入图；
- /modules：img2img registered=true + available=true（comfyui binding 在仓库内）。
"""
from __future__ import annotations

import dataclasses
import json
import time

import pytest

from app.core.config import Settings, WorkflowConfig
from app.main import create_app
from app.models import Image, JobStage
from app.workflows.img2img import DEFAULT_DENOISE, DENOISE_MAX, DENOISE_MIN, Img2ImgModule


# ===== 工具（与 test_phase51_contract 同构） =====

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


def import_one(client, name: str, data: bytes) -> dict:
    response = client.post("/api/v1/images/import", files=[("files", (name, data, "image/png"))])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["imported_count"] == 1, body
    return body["imported"][0]["image"]


# ===== 模块能力 =====

def test_img2img_capabilities_and_config_validation():
    capabilities = Img2ImgModule().capabilities()
    assert (capabilities.uses_seed, capabilities.input_kind, capabilities.output_kind) == (
        True, "image", "processed",
    )
    assert capabilities.input_required is True
    assert capabilities.parent_policy == "input_image"
    assert capabilities.output_cardinality == 1

    module = Img2ImgModule()
    assert module.validate_config({}).ok is True  # 缺省 = 默认强度
    assert module.validate_config({"denoise": DEFAULT_DENOISE}).ok is True
    assert module.validate_config({"denoise": DENOISE_MIN}).ok is True
    assert module.validate_config({"denoise": DENOISE_MAX}).ok is True
    assert module.validate_config({"denoise": 1.5}).ok is False
    assert module.validate_config({"denoise": 0.01}).ok is False
    assert module.validate_config({"denoise": "hot"}).ok is False
    assert module.validate_config({"surprise": 1}).ok is False


# ===== Job：img2img → processed 输出 =====

def test_img2img_job_produces_processed_child(mock_client, session, png_bytes):
    source = import_one(mock_client, "img2img_src.png", png_bytes)
    snapshot = make_snapshot(count=1, input_images=[{"role": "source", "image_id": source["id"]}],
                             workflow_modules=[{"module_id": "img2img",
                                                "config": {"denoise": 0.55}}])
    response = mock_client.post("/api/v1/jobs", json={"snapshot": snapshot})
    assert response.status_code == 201, response.text
    job = response.json()

    # config 单链：快照 → Job.workflow_snapshot
    module_ref = job["workflow_snapshot"]["modules"][0]
    assert module_ref["module_id"] == "img2img"
    assert module_ref["config"] == {"denoise": 0.55}

    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")
    stage0 = final["stages"][0]
    assert stage0["module_id"] == "img2img"
    stage_item = stage0["items"][0]
    assert stage_item["input_image_id"] == source["id"]
    assert stage_item["output_image_id"] and stage_item["output_image_id"] != source["id"]
    assert stage_item["seed"] is not None, "img2img uses_seed=true → StageItem 必须记录真实 Seed"

    # JobStage.config_json 物化（唯一事实源）
    stages = list(session.query(JobStage).filter(JobStage.job_id == job["id"]))
    assert json.loads(stages[0].config_json) == {"denoise": 0.55}

    # 输出图片语义：kind=processed + parent=输入图（由 ModuleCapabilities 驱动）
    output = session.get(Image, stage_item["output_image_id"])
    assert output.kind == "processed"
    assert output.parent_image_id == source["id"]
    assert output.seed == stage_item["seed"]


def test_img2img_then_upscale_chain(mock_client, session, png_bytes):
    source = import_one(mock_client, "chain_src.png", png_bytes)
    snapshot = make_snapshot(count=1, input_images=[{"role": "source", "image_id": source["id"]}],
                             workflow_modules=[{"module_id": "img2img"}, {"module_id": "upscale"}])
    job = mock_client.post("/api/v1/jobs", json={"snapshot": snapshot}).json()
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")
    assert [stage["module_id"] for stage in final["stages"]] == ["img2img", "upscale"]

    stage0_item = final["stages"][0]["items"][0]
    stage1_item = final["stages"][1]["items"][0]
    assert stage1_item["input_image_id"] == stage0_item["output_image_id"], \
        "Stage Gate：upscale 的输入 = img2img 输出"
    upscaled = session.get(Image, stage1_item["output_image_id"])
    assert upscaled.kind == "upscaled"
    assert upscaled.parent_image_id == stage0_item["output_image_id"]
    assert upscaled.seed is None, "upscale uses_seed=false → 不得携带假 Seed"


def test_img2img_requires_input_image(mock_client):
    response = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(workflow_modules=[{"module_id": "img2img"}]),
    })
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "INPUT_IMAGE_REQUIRED"


def test_img2img_rejects_bad_denoise(mock_client, png_bytes):
    source = import_one(mock_client, "bad_denoise.png", png_bytes)
    for bad in (1.5, "hot", True):
        response = mock_client.post("/api/v1/jobs", json={
            "snapshot": make_snapshot(
                input_images=[{"role": "source", "image_id": source["id"]}],
                workflow_modules=[{"module_id": "img2img", "config": {"denoise": bad}}],
            ),
        })
        assert response.status_code == 400, f"denoise={bad!r} 必须被拒绝: {response.text}"
        assert response.json()["error"]["code"] == "MODULE_CONFIG_INVALID"

    # 未知配置项同样拒绝（config 是正式契约，不允许随意塞参数）
    response = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(
            input_images=[{"role": "source", "image_id": source["id"]}],
            workflow_modules=[{"module_id": "img2img", "config": {"strength": 0.5}}],
        ),
    })
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MODULE_CONFIG_INVALID"


def test_img2img_resume_keeps_identity_and_input(mock_client, session, png_bytes):
    """Resume 剩余：继承 img2img 身份/config，并重新冻结输入图（不得丢失）。"""
    source = import_one(mock_client, "resume_src.png", png_bytes)
    snapshot = make_snapshot(count=3, input_images=[{"role": "source", "image_id": source["id"]}],
                             workflow_modules=[{"module_id": "img2img",
                                                "config": {"denoise": 0.55}}])
    job = mock_client.post("/api/v1/jobs", json={"snapshot": snapshot}).json()
    wait_for(mock_client, job["id"],
             lambda j: j["status"] == "RUNNING" and j["completed_count"] >= 1)
    mock_client.post(f"/api/v1/jobs/{job['id']}/cancel")
    parent = wait_for(mock_client, job["id"], lambda j: j["status"] == "CANCELLED")
    assert parent["completed_count"] < parent["requested_count"]

    child = mock_client.post(f"/api/v1/jobs/{job['id']}/resume-remaining").json()
    child_modules = child["workflow_snapshot"]["modules"]
    assert child_modules == parent["workflow_snapshot"]["modules"], "不得静默升级/丢 config"
    assert child_modules[0]["config"] == {"denoise": 0.55}

    # 输入图重新冻结到全部剩余槽位
    child_stages = list(session.query(JobStage).filter(JobStage.job_id == child["id"]))
    stage0_items = [item for stage in child_stages if stage.stage_index == 0
                    for item in stage.stage_items]
    assert stage0_items and all(item.input_image_id == source["id"] for item in stage0_items)

    final = wait_for(mock_client, child["id"], lambda j: j["status"] == "COMPLETED", timeout=90)
    assert final["completed_count"] == final["requested_count"]


# ===== /modules：img2img 真实可用（Gate C 依据） =====

def test_modules_api_exposes_img2img_available(client):
    modules = {item["module_id"]: item for item in client.get("/api/v1/modules").json()}
    img2img = modules["img2img"]
    assert img2img["registered"] is True
    assert img2img["available"] is True, img2img
    assert img2img["provider"] == "comfyui"
    assert img2img["binding_version"] == "v1"
    assert img2img["input_required"] is True and img2img["output_kind"] == "processed"