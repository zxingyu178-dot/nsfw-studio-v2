"""ComfyUI 真实集成测试（Phase 3 §二十六：1 张基础生成最短真实链路）。

仅在本机 ComfyUI 在线时运行；CI / 其他机器自动跳过。
测试走完整生产链：POST /jobs → 队列 → 模块 → ComfyUIAdapter → DataRoot → Gallery。

注意（§二十六）：不再重跑长测试；只保留最短真实链路。
"""
from __future__ import annotations

import asyncio
import time

import pytest

from app.core.config import Settings, WorkflowConfig
from app.engine.comfyui import ComfyUIAdapter
from app.main import create_app

_COMFY_URL = "http://127.0.0.1:8188"


def _comfy_available() -> bool:
    import os
    # Hermetic 模式（tests/conftest.py 置位）：即使本机 8188 在线也绝不跑真实 POST /prompt
    if os.environ.get("NSFW_STUDIO_HERMETIC"):
        return False
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
