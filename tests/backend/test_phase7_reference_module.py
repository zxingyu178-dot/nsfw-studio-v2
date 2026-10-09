"""Phase 7 Task6：Reference Module（reference_generate v1）离线 Mock 回归。

- 能力声明：reference 槽必填、生成型、输出 kind=original 且挂到参考图下；
- Job 创建期 Slot 门禁：缺 reference → INPUT_IMAGE_REQUIRED；给 source → UNUSED_INPUT_IMAGE；
- config 单链：resolution 经 Workbench → JobStage.config_json → 引擎请求；
- reference_generate → upscale 链式（Stage Gate）；
- /modules：registered + available（仓库内已有 comfyui binding）。
"""
from __future__ import annotations

import dataclasses
import json
import time

import pytest

from app.core.config import Settings, WorkflowConfig
from app.main import create_app
from app.models import Image, JobStage
from app.workflows.reference_generate import (
    RESOLUTION_DEFAULT,
    RESOLUTION_MAX,
    RESOLUTION_MIN,
    ReferenceGenerateModule,
)


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
    raise AssertionError(f"等待任务状态超时: {json.dumps(last, ensure_ascii=False)[:400]}")


def import_one(client, name: str, data: bytes) -> dict:
    response = client.post("/api/v1/images/import", files=[("files", (name, data, "image/png"))])
    assert response.status_code == 201, response.text
    return response.json()["imported"][0]["image"]


# ===== 能力与 config =====

def test_reference_capabilities_and_config_validation():
    capabilities = ReferenceGenerateModule().capabilities()
    assert capabilities.input_slots and capabilities.input_slots[0].role == "reference"
    assert capabilities.input_slots[0].required is True
    assert capabilities.input_slots[0].max_count == 1
    assert capabilities.is_generative is True
    assert capabilities.allowed_job_kinds == ("generate",)
    assert capabilities.can_start_from_image is True
    assert (capabilities.uses_seed, capabilities.input_kind, capabilities.output_kind) == (
        True, "image", "original",
    )
    assert capabilities.parent_policy == "input_image"
    assert capabilities.size_mode == "input"

    module = ReferenceGenerateModule()
    assert module.validate_config({}).ok is True
    assert module.validate_config({"resolution": RESOLUTION_DEFAULT}).ok is True
    assert module.validate_config({"resolution": RESOLUTION_MIN}).ok is True
    assert module.validate_config({"resolution": RESOLUTION_MAX}).ok is True
    assert module.validate_config({"resolution": 256}).ok is False
    assert module.validate_config({"resolution": 4096}).ok is False
    assert module.validate_config({"resolution": "big"}).ok is False
    assert module.validate_config({"resolution": True}).ok is False
    assert module.validate_config({"surprise": 1}).ok is False


# ===== Slot 门禁 =====

def test_reference_requires_reference_slot(mock_client):
    response = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(workflow_modules=[{"module_id": "reference_generate"}]),
    })
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "INPUT_IMAGE_REQUIRED"


def test_reference_rejects_source_role(mock_client, png_bytes):
    source = import_one(mock_client, "ref_wrong_role.png", png_bytes)
    response = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(
            input_images=[{"role": "source", "image_id": source["id"]}],
            workflow_modules=[{"module_id": "reference_generate"}],
        ),
    })
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "UNUSED_INPUT_IMAGE"


# ===== 端到端（Mock 引擎）：参考图 → original 输出，挂到参考图下 =====

def test_reference_job_produces_original_child(mock_client, session, png_bytes):
    reference = import_one(mock_client, "ref_src.png", png_bytes)
    snapshot = make_snapshot(
        count=1,
        input_images=[{"role": "reference", "image_id": reference["id"]}],
        workflow_modules=[{"module_id": "reference_generate", "config": {"resolution": 768}}],
    )
    response = mock_client.post("/api/v1/jobs", json={"snapshot": snapshot})
    assert response.status_code == 201, response.text
    job = response.json()

    module_ref = job["workflow_snapshot"]["modules"][0]
    assert module_ref["module_id"] == "reference_generate"
    assert module_ref["config"] == {"resolution": 768}

    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")
    stage0 = final["stages"][0]
    assert stage0["module_id"] == "reference_generate"
    stage_item = stage0["items"][0]
    assert stage_item["input_image_id"] == reference["id"]
    assert stage_item["output_image_id"] and stage_item["output_image_id"] != reference["id"]
    assert stage_item["seed"] is not None, "uses_seed=true → StageItem 必须记录真实 Seed"

    # config_json 唯一事实源 + 引擎请求参数（含参考分辨率）
    stages = list(session.query(JobStage).filter(JobStage.job_id == job["id"]))
    assert json.loads(stages[0].config_json) == {"resolution": 768}
    request = mock_client.app.state.adapter.submitted_requests[-1]
    assert request.binding.module_id == "reference_generate"
    assert request.parameters["input_image"], "参考图必须已上传为引擎侧引用名"
    assert request.parameters["resolution"] == 768
    assert request.parameters["positive_prompt"], "Prompt 必须进入引擎请求"
    assert request.parameters["negative_prompt"] == "blurry"

    # 输出语义：kind=original、parent=参考图（ModuleCapabilities 驱动）
    output = session.get(Image, stage_item["output_image_id"])
    assert output.kind == "original"
    assert output.parent_image_id == reference["id"]
    assert output.seed == stage_item["seed"]

    # 上传登记：reference 图片被上传（Studio 命名契约）
    assert any(image_id == reference["id"] for _name, image_id in mock_client.app.state.adapter.uploaded_inputs)


def test_reference_then_upscale_chain(mock_client, session, png_bytes):
    reference = import_one(mock_client, "ref_chain_src.png", png_bytes)
    snapshot = make_snapshot(
        count=1,
        input_images=[{"role": "reference", "image_id": reference["id"]}],
        workflow_modules=[{"module_id": "reference_generate"}, {"module_id": "upscale"}],
    )
    job = mock_client.post("/api/v1/jobs", json={"snapshot": snapshot}).json()
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")
    assert [stage["module_id"] for stage in final["stages"]] == ["reference_generate", "upscale"]
    stage0_item = final["stages"][0]["items"][0]
    stage1_item = final["stages"][1]["items"][0]
    assert stage1_item["input_image_id"] == stage0_item["output_image_id"]
    upscaled = session.get(Image, stage1_item["output_image_id"])
    assert upscaled.kind == "upscaled"
    assert upscaled.parent_image_id == stage0_item["output_image_id"]


# ===== /modules 可用性（comfyui binding 在仓库内） =====

def test_modules_api_exposes_reference_generate(client):
    modules = {item["module_id"]: item for item in client.get("/api/v1/modules").json()}
    reference = modules["reference_generate"]
    assert reference["registered"] is True
    assert reference["available"] is True, reference
    assert reference["provider"] == "comfyui"
    assert reference["binding_version"] == "v1"
    assert reference["input_slots"] == [{
        "role": "reference", "required": True, "max_count": 1,
        "description": "参考图（人物/主体）；可直接使用 Face Asset 的参考图",
    }]
    assert reference["is_generative"] is True