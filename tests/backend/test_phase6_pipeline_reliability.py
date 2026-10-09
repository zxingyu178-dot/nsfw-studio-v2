"""Phase 6：Pipeline 可靠性收口回归（全部离线 Mock）。

锁定用户审查发现的真实缺口：
- Task1 Image → Workbench 选择"最近的生成上下文"（不再永远取树根）；
- Task2 前端身份保留（前端侧，见 frontend 测试/人工验收）；
- Task3 Recipe 固定 Seed 归一化；
- Task4 Pipeline 顺序保持 + 重复模块拒绝；
- Task5 Module Availability 收紧；
- Task6 Img2ImgModule.execute Prompt 契约；
- Task7 generation_mode 往返；
- Task8 Module 参数元数据驱动；
- Task9 size_mode / 有效尺寸语义。
"""
from __future__ import annotations

import dataclasses
import json
import time

import pytest

from app.core.config import Settings, WorkflowConfig
from app.main import create_app
from app.models import Image


# ===== 工具（与 test_phase51_img2img 同构） =====

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


def gallery(client, job_id: str) -> list[dict]:
    return client.get("/api/v1/images", params={"job_id": job_id, "limit": 200}).json()["items"]


def run_generate(client, snapshot: dict) -> dict:
    response = client.post("/api/v1/jobs", json={"snapshot": snapshot})
    assert response.status_code == 201, response.text
    job = response.json()
    return wait_for(client, job["id"], lambda j: j["status"] == "COMPLETED")


def workbench_of(client, image_id: str) -> dict:
    response = client.get(f"/api/v1/images/{image_id}/workbench")
    assert response.status_code == 200, response.text
    return response.json()


# ===== Task1：Image → Workbench 最近的生成上下文 =====

def test_workbench_import_then_img2img_restores_img2img(mock_client, session, png_bytes):
    """import → img2img：旧逻辑取树根（导入图无 Job）会 404；新逻辑恢复 Img2Img Job。"""
    source = import_one(mock_client, "p6_img2img_src.png", png_bytes)
    final = run_generate(mock_client, make_snapshot(
        input_images=[{"role": "source", "image_id": source["id"]}],
        workflow_modules=[{"module_id": "img2img", "config": {"denoise": 0.55}}],
    ))
    processed_id = final["stages"][0]["items"][0]["output_image_id"]
    processed = session.get(Image, processed_id)
    assert processed.kind == "processed" and processed.parent_image_id == source["id"]

    body = workbench_of(mock_client, processed_id)
    modules = body["snapshot"]["workflow_modules"]
    assert [module["module_id"] for module in modules] == ["img2img"]
    assert modules[0]["config"] == {"denoise": 0.55}
    assert body["snapshot"]["input_images"][0]["image_id"] == source["id"], \
        "恢复的工作台必须携带原输入图（否则 Img2Img 无法重现）"
    # Seed = 生成上下文图片（img2img 输出）的真实 Seed
    assert body["seed"] == processed.seed and body["seed"] is not None
    assert body["snapshot"]["seed_mode"] == "random"


def test_workbench_img2img_then_upscale_still_restores_img2img(mock_client, session, png_bytes):
    """import → img2img → upscale（同一 generate Job 内嵌后处理）：仍恢复 Img2Img，
    Seed 取 img2img Stage 的真实 Seed（upscale 输出 Seed 为 NULL，不能拿它当上下文）。"""
    source = import_one(mock_client, "p6_chain_src.png", png_bytes)
    final = run_generate(mock_client, make_snapshot(
        input_images=[{"role": "source", "image_id": source["id"]}],
        workflow_modules=[{"module_id": "img2img", "config": {"denoise": 0.55}},
                          {"module_id": "upscale"}],
    ))
    assert [stage["module_id"] for stage in final["stages"]] == ["img2img", "upscale"]
    img2img_out_id = final["stages"][0]["items"][0]["output_image_id"]
    upscaled_id = final["stages"][1]["items"][0]["output_image_id"]
    img2img_out = session.get(Image, img2img_out_id)
    upscaled = session.get(Image, upscaled_id)
    assert upscaled.seed is None, "前置条件：upscale 输出无 Seed"

    body = workbench_of(mock_client, upscaled_id)
    modules = body["snapshot"]["workflow_modules"]
    assert [module["module_id"] for module in modules] == ["img2img", "upscale"]
    assert modules[0]["module_id"] == "img2img", "Primary 必须是 Img2Img（不是导入图 / basic）"
    assert body["seed"] == img2img_out.seed and body["seed"] is not None, \
        "Seed 必须取 img2img 的真实 Seed，而不是 upscale 的 NULL"


def test_workbench_basic_then_upscale_restores_basic(mock_client, session, png_bytes):
    """basic → upscale（同一 generate Job）：恢复 basic，Seed = 原图真实 Seed。"""
    final = run_generate(mock_client, make_snapshot(
        workflow_modules=[{"module_id": "basic_generate"}, {"module_id": "upscale"}],
    ))
    images = gallery(mock_client, final["id"])
    original = next(image for image in images if image["kind"] == "original")
    upscaled = next(image for image in images if image["kind"] == "upscaled")

    body = workbench_of(mock_client, upscaled["id"])
    modules = body["snapshot"]["workflow_modules"]
    assert [module["module_id"] for module in modules] == ["basic_generate", "upscale"]
    assert body["snapshot"]["structured_prompt"]["style"] == "anime"
    assert body["seed"] == original["seed"] and body["seed"] is not None


def test_workbench_basic_then_img2img_then_upscale_restores_img2img(mock_client, session, png_bytes):
    """basic → img2img → upscale：恢复 Img2Img（不是 basic，也不是树根），
    Seed 取 img2img 的真实 Seed（不是 basic 原图 Seed）。"""
    basic_final = run_generate(mock_client, make_snapshot(count=1))
    original = gallery(mock_client, basic_final["id"])[0]

    final = run_generate(mock_client, make_snapshot(
        input_images=[{"role": "source", "image_id": original["id"]}],
        workflow_modules=[{"module_id": "img2img", "config": {"denoise": 0.55}},
                          {"module_id": "upscale"}],
    ))
    img2img_out_id = final["stages"][0]["items"][0]["output_image_id"]
    upscaled_id = final["stages"][1]["items"][0]["output_image_id"]
    img2img_out = session.get(Image, img2img_out_id)

    body = workbench_of(mock_client, upscaled_id)
    modules = body["snapshot"]["workflow_modules"]
    assert modules[0]["module_id"] == "img2img", "距离最近的生成上下文是 img2img 输出"
    assert body["seed"] == img2img_out.seed, "不是树根（basic 原图）Seed"
    assert body["snapshot"]["input_images"][0]["image_id"] == original["id"]


def test_workbench_pure_import_still_has_no_context(mock_client, png_bytes):
    """纯外部导入图：全链无真实生成图 → 404 IMAGE_NO_GENERATION_CONTEXT。"""
    imported = import_one(mock_client, "p6_pure_import.png", png_bytes)
    response = mock_client.get(f"/api/v1/images/{imported['id']}/workbench")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "IMAGE_NO_GENERATION_CONTEXT"