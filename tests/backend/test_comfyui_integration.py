"""ComfyUI 真实集成测试（Phase 2 规范 §五十九：1/3/8 张）。

仅在本机 ComfyUI 在线时运行；CI / 其他机器自动跳过。
测试走完整生产链：POST /jobs → 队列 → ComfyUIAdapter → 图片导入 DataRoot → Gallery。
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
    try:
        adapter = ComfyUIAdapter({}, {"url": _COMFY_URL})
        return asyncio.run(adapter.health()).online
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _comfy_available(), reason="本机 ComfyUI 未运行")


def comfy_settings(settings: Settings) -> Settings:
    return dataclasses_replace_workflow(settings, {
        "provider": "comfyui",
        "module_id": "basic_generate",
        "module_version": "v1",
        "binding_version": "v1",
        "options": {"worker_poll_interval_ms": 200, "engine_poll_ms": 1000},
    })


def dataclasses_replace_workflow(settings: Settings, engine: dict) -> Settings:
    import dataclasses

    return dataclasses.replace(settings, workflow=WorkflowConfig(raw={"engine": engine}))


def make_snapshot(count, seed=410100):
    return {
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
        "seed_mode": "fixed",   # 集成测试用固定基础 Seed，保证可复现且断言 seed+index
        "seed": seed,
        "workflow_modules": [],
    }


def wait_for(client, job_id, predicate, timeout):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/api/v1/jobs/{job_id}").json()
        if predicate(last):
            return last
        time.sleep(2)
    raise AssertionError(f"超时: {last.get('status') if last else '无'}")


@pytest.fixture()
def real_client(settings):
    from fastapi.testclient import TestClient

    app = create_app(comfy_settings(settings))
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("count", [1, 3, 8])
def test_real_generation(real_client, count):
    """真实生成 1/3/8 张：顺序执行、Seed=base+index、图片逐张入 Gallery、元数据完整。"""
    response = real_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(count),
        "client_request_id": f"integration-{count}",
    })
    assert response.status_code == 201
    job = response.json()
    assert job["provider"] == "comfyui" and job["workflow_hash"]

    timeout = 600 + count * 240  # 首图含模型加载
    final = wait_for(real_client, job["id"], lambda j: j["status"] in ("COMPLETED", "FAILED"), timeout)

    assert final["status"] == "COMPLETED", f"生成失败: {final.get('error_message')}"
    assert final["completed_count"] == count
    seeds = sorted(item["seed"] for item in final["items"])
    assert seeds == [410100 + i for i in range(count)], "Seed = base + item_index"
    engine_ids = [item["engine_job_id"] for item in final["items"]]
    assert len(set(engine_ids)) == count, "每张图独立引擎任务"

    # 图片正式进入 Studio（DataRoot + 数据库）
    images = real_client.get("/api/v1/images", params={"job_id": job["id"], "limit": 200}).json()
    assert images["total"] == count
    for image in images["items"]:
        assert image["file_path"].startswith("images/originals/")
        assert image["width"] == 640 and image["height"] == 960
        assert image["source"] == "comfyui"
        content = real_client.get(f"/api/v1/images/{image['id']}/content")
        assert content.status_code == 200 and len(content.content) > 1000

    # Workbench Snapshot 完整（规范 §五十九）
    snapshot = real_client.get(f"/api/v1/jobs/{job['id']}").json()["workbench_snapshot"]
    assert snapshot["structured_prompt"]["scene"] == "quiet library, soft window light"
    assert snapshot["seed_mode"] == "fixed"
