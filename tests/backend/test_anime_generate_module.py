"""anime_generate（Anima 2.9B 动漫链）离线 Mock 回归。

- 契约与 basic_generate 同构：positive/negative/width/height/seed、explicit 尺寸、无输入槽；
- 身份独立：module_id=anime_generate、标题/描述为动漫向（写实请用 basic_generate）；
- /modules：registered + available（仓库内已有 comfyui binding）；
- 端到端（Mock 引擎）：创建 → COMPLETED → kind=original / seed 记录 / 引擎请求参数正确；
- anime_generate → upscale 链式合法。
"""
from __future__ import annotations

import dataclasses
import json
import time

import pytest

from app.core.config import Settings, WorkflowConfig
from app.engine import release
from app.main import create_app
from app.models import Image, JobStage
from app.workflows.anime_generate import AnimeGenerateModule
from app.workflows.basic_generate import BasicGenerateModule


def make_snapshot(count: int = 1, **overrides) -> dict:
    snapshot = {
        "prompt_mode": "full",
        "full_prompt": "1girl, red dress, night city street, anime style, masterpiece",
        "negative_prompt": "worst quality, low quality, blurry",
        "count": count,
        "width": 768,
        "height": 1024,
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


# ===== 能力声明：与 basic_generate 同契约、不同身份 =====

def test_anime_capabilities_mirror_basic_contract_with_anime_identity():
    anime = AnimeGenerateModule().capabilities()
    basic = BasicGenerateModule().capabilities()
    assert anime.module_id == "anime_generate" and anime.module_version == "v1"
    assert "Anima" in anime.title and "动漫" in anime.title
    assert anime.description != basic.description
    # 契约完全一致（尺寸/seed/输入/输出语义）
    assert anime.uses_seed is True
    assert anime.input_kind == "none" and anime.input_required is False
    assert anime.input_slots == ()
    assert anime.output_kind == "original" and anime.parent_policy == "none"
    assert anime.size_mode == "explicit"
    assert anime.allowed_job_kinds == ("generate",)
    assert anime.can_start_from_image is False
    assert anime.is_generative is True
    assert [spec.name for spec in anime.parameters] == [
        spec.name for spec in basic.parameters
    ]


# ===== 端到端（Mock）：动漫模块任务完成，输出 original =====

def force_unreleased(monkeypatch):
    monkeypatch.setattr(release, "load_release_manifest", lambda: {"modules": {
        "anime_generate": {"bindings": {"v1": {
            "dependencies_ready": True, "real_gate_passed": False,
            "hardware_status": "experimental", "default_profile_verified": False,
            "notes": "test-only unreleased",
        }}},
    }})


def test_anime_job_rejected_when_manifest_not_released(mock_client, monkeypatch):
    """W1.1-1：manifest 未放行时，服务端拒绝创建 Job（不能只靠前端隐藏）。"""
    force_unreleased(monkeypatch)
    response = mock_client.post("/api/v1/jobs", json={
        "source": "doubao",
        "client_request_id": "anime-e2e-1",
        "snapshot": make_snapshot(
            count=1, workflow_modules=[{"module_id": "anime_generate"}],
        ),
    })
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "WORKFLOW_NOT_RELEASED"


def test_anime_rejects_input_image(mock_client, monkeypatch, png_bytes):
    """动漫模块不消费输入图（无输入槽）→ 携带输入图必须被拒绝。"""
    force_unreleased(monkeypatch)
    imported = mock_client.post(
        "/api/v1/images/import", files=[("files", ("anime_in.png", png_bytes, "image/png"))]
    ).json()["imported"][0]["image"]
    response = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(
            input_images=[{"role": "source", "image_id": imported["id"]}],
            workflow_modules=[{"module_id": "anime_generate"}],
        ),
    })
    # 放行门禁先于输入槽校验：未放行模块直接 WORKFLOW_NOT_RELEASED。
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "WORKFLOW_NOT_RELEASED"


def test_anime_then_upscale_chain_rejected(mock_client, monkeypatch):
    force_unreleased(monkeypatch)
    response = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(
            count=1,
            workflow_modules=[{"module_id": "anime_generate"}, {"module_id": "upscale"}],
        ),
    })
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "WORKFLOW_NOT_RELEASED"


# ===== /modules：注册 + 可用（binding 在仓库内） =====

def test_modules_api_exposes_anime_generate(client):
    modules = {item["module_id"]: item for item in client.get("/api/v1/modules").json()}
    anime = modules["anime_generate"]
    assert anime["registered"] is True
    assert anime["available"] is True, anime
    assert anime["provider"] == "comfyui"
    assert anime["binding_version"] == "v1"
    # W1.1-3：当前 binding 已有真实 Studio COMPLETED 证据（2026-10-20），
    # 不能沿用 W0 的“未验收”推断。
    assert anime["release_status"]["real_gate_passed"] is True
    assert anime["release_status"]["ready_to_run"] is True
    assert anime["release_status"]["hardware_status"] == "slow"
    assert anime["release_status"]["default_profile_verified"] is False
    assert anime["is_generative"] is True
    assert anime["input_slots"] == []
    assert anime["title"] == "动漫生图（Anima）"