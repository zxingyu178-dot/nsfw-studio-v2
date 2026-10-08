"""ComfyUI 真实集成测试（Phase 3 §二十六：1 张基础 + 1 张真实高清 + 图库单张高清）。

仅在本机 ComfyUI 在线时运行；CI / 其他机器自动跳过。
测试走完整生产链：POST /jobs（或 /images/upscale）→ 队列 → 模块 → ComfyUIAdapter → DataRoot → Gallery。

注意（§二十六）：不再重跑 1/3/8 张长测试；只保留三条最短真实链路。
"""
from __future__ import annotations

import asyncio
import struct
import time
import zlib

import pytest

from app.core.config import Settings, WorkflowConfig
from app.engine.comfyui import ComfyUIAdapter
from app.main import create_app

_COMFY_URL = "http://127.0.0.1:8188"


def _comfy_available() -> bool:
    try:
        adapter = ComfyUIAdapter({}, {"url": _COMFY_URL})
        return asyncio.run(adapter.health()).online
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _comfy_available(), reason="本机 ComfyUI 未运行")


def comfy_settings(settings: Settings) -> Settings:
    import dataclasses

    return dataclasses.replace(settings, workflow=WorkflowConfig(raw={"engine": {
        "provider": "comfyui",
        "module_id": "basic_generate",
        "module_version": "v1",
        "binding_version": "v1",
        "modules": {
            "basic_generate": {"module_version": "v1", "binding_version": "v1"},
            "upscale": {"module_version": "v1", "binding_version": "v1"},
        },
        "options": {"worker_poll_interval_ms": 500, "engine_poll_ms": 1000},
    }}))


def make_snapshot(count=1, modules=(), **overrides):
    snapshot = {
        "prompt_mode": "structured",
        "structured_prompt": {
            "style": "photograph",
            "face": "",
            "clothing": "white shirt",
            "pose": "",
            "scene": "quiet library, soft window light",
            "composition": "",
            "lighting": "",
            "extra": "high quality",
        },
        "full_prompt": "",
        "negative_prompt": "blurry, lowres",
        "selected_assets": {},
        "width": 640, "height": 960,
        "count": count,
        # §0.4：多张必须随机；真实链路不再使用固定 Seed
        "seed_mode": "random",
        "seed": None,
        "workflow_modules": [{"module_id": module_id} for module_id in modules],
    }
    snapshot.update(overrides)
    return snapshot


def make_png(width: int, height: int, color=(200, 60, 40)) -> bytes:
    """纯标准库生成合法 PNG（供图库高清真实链路使用，避免依赖 Pillow）。"""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def wait_for(client, job_id, predicate, timeout):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/api/v1/jobs/{job_id}").json()
        if predicate(last):
            return last
        time.sleep(3)
    raise AssertionError(f"超时: {last.get('status') if last else '无'} / {last.get('error_message') if last else ''}")


@pytest.fixture()
def real_client(settings):
    from fastapi.testclient import TestClient

    app = create_app(comfy_settings(settings))
    with TestClient(app) as test_client:
        yield test_client


def test_real_basic_generation_smoke(real_client):
    """真实 1 张基础生成：Job → BasicGenerateModule → ComfyUI → Image → Gallery（§二十六）。"""
    job = real_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(count=1),
        "client_request_id": "p3-real-basic-1",
    }).json()
    assert job["workflow_snapshot"]["modules"][0]["module_id"] == "basic_generate"

    final = wait_for(real_client, job["id"], lambda j: j["status"] in ("COMPLETED", "FAILED"),
                     timeout=1200)  # 首图含模型加载（本机约 7 分钟）
    assert final["status"] == "COMPLETED", f"生成失败: {final.get('error_message')}"
    assert final["completed_count"] == 1
    assert final["stages"][0]["module_id"] == "basic_generate"
    assert final["stages"][0]["status"] == "COMPLETED"
    assert final["items"][0]["image_id"], "COMPLETED 必须伴随 Studio Image"

    images = real_client.get("/api/v1/images", params={"job_id": job["id"]}).json()
    assert images["total"] == 1
    image = images["items"][0]
    assert image["kind"] == "original" and image["file_path"].startswith("images/originals/")
    assert image["width"] == 640 and image["height"] == 960


def test_real_pipeline_basic_then_upscale(real_client):
    """真实基础生成 → 真实高清：1 张原图全部完成后再进入高清 Stage（§二十六/§六）。"""
    job = real_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(count=1, modules=("basic_generate", "upscale")),
        "client_request_id": "p3-real-pipeline-1",
    }).json()
    modules = [module["module_id"] for module in job["workflow_snapshot"]["modules"]]
    assert modules == ["basic_generate", "upscale"]
    assert job["stages"][0]["workflow_hash"] and job["stages"][1]["workflow_hash"]

    final = wait_for(real_client, job["id"], lambda j: j["status"] in ("COMPLETED", "FAILED"),
                     timeout=2400)
    assert final["status"] == "COMPLETED", f"失败: {final.get('error_message')}"

    stages = final["stages"]
    assert [stage["module_id"] for stage in stages] == ["basic_generate", "upscale"]
    assert all(stage["status"] == "COMPLETED" for stage in stages)
    stage1_items = stages[1]["items"]
    assert stage1_items[0]["input_image_id"] == stages[0]["items"][0]["output_image_id"]

    images = real_client.get("/api/v1/images", params={"job_id": job["id"], "limit": 200}).json()
    assert images["total"] == 2
    original = next(image for image in images["items"] if image["kind"] == "original")
    upscaled = next(image for image in images["items"] if image["kind"] == "upscaled")
    assert original["file_path"].startswith("images/originals/")
    assert upscaled["file_path"].startswith("images/upscaled/")
    assert upscaled["parent_image_id"] == original["id"]
    assert upscaled["width"] == original["width"] * 4 and upscaled["height"] == original["height"] * 4, \
        "4x-UltraSharp 必须产出 4 倍尺寸高清"
    # 原图不被覆盖：内容仍可读取
    assert real_client.get(f"/api/v1/images/{original['id']}/content").status_code == 200


def test_real_gallery_upscale_only(real_client):
    """图库已有图片 → 单独高清（upscale-only process Job，同一 Worker/同一 UpscaleModule）。"""
    from app.services import image_service
    from app.storage.manager import StorageManager

    source_png = make_png(64, 64)
    with real_client.app.state.session_factory() as session:
        storage = StorageManager(real_client.app.state.settings)
        source = image_service.import_engine_output(
            session, storage, data=source_png, original_filename="source.png", source="import",
        )
        source_id = source.id

    response = real_client.post("/api/v1/images/upscale", json={"image_ids": [source_id]})
    assert response.status_code == 201
    job = response.json()
    assert job["job_kind"] == "process"
    assert [stage["module_id"] for stage in job["stages"]] == ["upscale"]

    final = wait_for(real_client, job["id"], lambda j: j["status"] in ("COMPLETED", "FAILED"),
                     timeout=900)
    assert final["status"] == "COMPLETED", f"失败: {final.get('error_message')}"
    assert final["stages"][0]["items"][0]["input_image_id"] == source_id

    images = real_client.get("/api/v1/images", params={"job_id": job["id"]}).json()
    assert images["total"] == 1
    upscaled = images["items"][0]
    assert upscaled["kind"] == "upscaled"
    assert upscaled["parent_image_id"] == source_id
    assert upscaled["width"] == 256 and upscaled["height"] == 256  # 64 × 4

    versions = real_client.get(f"/api/v1/images/{source_id}/versions").json()
    assert [child["id"] for child in versions["children"]] == [upscaled["id"]]