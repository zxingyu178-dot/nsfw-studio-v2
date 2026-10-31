"""Agent 提交端点（Phase 0.34）：默认关闭 / Bearer token / 限速 / 幂等 / 参数校验。"""
from __future__ import annotations

import dataclasses
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import ENV_AGENT_RATE_LIMIT, ENV_AGENT_TOKEN, Settings, WorkflowConfig
from app.engine import release
from app.main import create_app
from app.models import Job, JobStage, Prompt


def mock_settings(settings: Settings) -> Settings:
    return dataclasses.replace(
        settings,
        workflow=WorkflowConfig(raw={"engine": {"provider": "mock", "options": {
            "worker_poll_interval_ms": 30, "engine_poll_ms": 20,
        }}}),
        agent={},  # 测试不读取本机 config.local 的 agent 配置
    )


@pytest.fixture()
def agent_client(settings):
    app = create_app(mock_settings(settings))
    with TestClient(app) as client:
        yield client


def payload(**overrides):
    body = {
        "prompt": "1girl, silver hair, kimono, shrine, masterpiece",
        "negative_prompt": "low quality",
        "module_id": "basic_generate",
        "width": 768,
        "height": 1024,
        "count": 1,
        "client_request_id": f"test_{uuid.uuid4().hex[:10]}",
    }
    body.update(overrides)
    return body


def db_counts(session) -> tuple[int, int, int]:
    """(Prompt, Job, JobStage) 行数；用于断言拒绝请求不产生副作用。"""
    return (
        session.query(Prompt).count(),
        session.query(Job).count(),
        session.query(JobStage).count(),
    )


def test_agent_api_disabled_without_token(agent_client, monkeypatch):
    """未配置 token = 默认关闭，返回 403 AGENT_API_DISABLED。"""
    monkeypatch.delenv(ENV_AGENT_TOKEN, raising=False)
    response = agent_client.post("/api/v1/agent/jobs", json=payload())
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AGENT_API_DISABLED"


def test_missing_bearer_token_rejected(agent_client, monkeypatch):
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-1")
    response = agent_client.post("/api/v1/agent/jobs", json=payload())
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AGENT_TOKEN_MISSING"


def test_wrong_bearer_token_rejected(agent_client, monkeypatch):
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-2")
    response = agent_client.post(
        "/api/v1/agent/jobs", json=payload(), headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AGENT_TOKEN_INVALID"


def test_valid_token_creates_queued_job(agent_client, monkeypatch):
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-3")
    headers = {"Authorization": "Bearer test-token-3"}
    body = payload(seed=42)
    response = agent_client.post("/api/v1/agent/jobs", json=body, headers=headers)
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["source"] == "agent"
    assert job["status"] in ("QUEUED", "RUNNING")
    assert job["module_id"] == "basic_generate"
    assert job["workbench_snapshot"]["seed_mode"] == "fixed"
    assert job["workbench_snapshot"]["seed"] == 42

    detail = agent_client.get(f"/api/v1/jobs/{job['id']}").json()
    assert "silver hair" in (detail.get("positive_prompt_snapshot") or "")


def test_agent_cannot_bypass_release_gate(agent_client, monkeypatch):
    """W1.1-1：Agent 与 Web 共用服务端 manifest，未放行模块直接拒绝。"""
    # 生产 manifest 当前按真实证据放行 anime；门禁测试用临时清单强制未登记。
    monkeypatch.setattr(release, "load_release_manifest", lambda: {"modules": {}})
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-gate")
    headers = {"Authorization": "Bearer test-token-gate"}
    response = agent_client.post(
        "/api/v1/agent/jobs", json=payload(module_id="anime_generate"), headers=headers,
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "WORKFLOW_NOT_RELEASED"


def test_idempotent_replay_returns_same_job(agent_client, monkeypatch):
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-4")
    headers = {"Authorization": "Bearer test-token-4"}
    body = payload(upscale=True)
    first = agent_client.post("/api/v1/agent/jobs", json=body, headers=headers)
    second = agent_client.post("/api/v1/agent/jobs", json=body, headers=headers)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["idempotent_replay"] is True


def test_rate_limit_rejects_excess_submissions(agent_client, monkeypatch):
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-rate")
    monkeypatch.setenv(ENV_AGENT_RATE_LIMIT, "1")
    headers = {"Authorization": "Bearer test-token-rate"}
    first = agent_client.post("/api/v1/agent/jobs", json=payload(), headers=headers)
    second = agent_client.post("/api/v1/agent/jobs", json=payload(), headers=headers)
    assert first.status_code == 201
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "AGENT_RATE_LIMITED"


def test_prompt_too_long_and_invalid_module_rejected(agent_client, monkeypatch):
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-5")
    monkeypatch.setenv(ENV_AGENT_RATE_LIMIT, "0")  # 该用例关掉限速
    headers = {"Authorization": "Bearer test-token-5"}
    too_long = agent_client.post(
        "/api/v1/agent/jobs", json=payload(prompt="x" * 10001), headers=headers,
    )
    assert too_long.status_code == 422
    bad_module = agent_client.post(
        "/api/v1/agent/jobs", json=payload(module_id="upscale"), headers=headers,
    )
    # W1.2：upscale 是处理型模块（input_required=true / allowed_job_kinds 含 process），
    # 能力校验必须明确拒绝，不能静默降级到 basic_generate。
    assert bad_module.status_code == 400
    assert bad_module.json()["error"]["code"] == "AGENT_MODULE_NOT_TEXT_GENERATE"


# ===== W1.2-B/C：默认工作流、显式选择、能力门禁与副作用 =====

def test_module_id_omitted_uses_server_default(agent_client, monkeypatch):
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-default")
    monkeypatch.setenv(ENV_AGENT_RATE_LIMIT, "0")
    headers = {"Authorization": "Bearer test-token-default"}
    response = agent_client.post(
        "/api/v1/agent/jobs", json=payload(module_id=None), headers=headers,
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["module_id"] == "basic_generate"
    assert job["workflow_snapshot"]["modules"][0]["module_id"] == "basic_generate"
    # 快照必须记录实际使用的模块，不能只记录空的默认选择
    assert job["workbench_snapshot"]["workflow_modules"][0]["module_id"] == "basic_generate"


def test_explicit_basic_and_anime_accepted(agent_client, monkeypatch):
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-explicit")
    monkeypatch.setenv(ENV_AGENT_RATE_LIMIT, "0")
    headers = {"Authorization": "Bearer test-token-explicit"}
    basic = agent_client.post(
        "/api/v1/agent/jobs", json=payload(module_id="basic_generate"), headers=headers,
    )
    anime = agent_client.post(
        "/api/v1/agent/jobs", json=payload(module_id="anime_generate"), headers=headers,
    )
    assert basic.status_code == 201, basic.text
    assert anime.status_code == 201, anime.text
    assert basic.json()["module_id"] == "basic_generate"
    assert anime.json()["module_id"] == "anime_generate"


def test_unknown_module_rejected_without_side_effects(agent_client, session, monkeypatch):
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-unknown")
    monkeypatch.setenv(ENV_AGENT_RATE_LIMIT, "0")
    headers = {"Authorization": "Bearer test-token-unknown"}
    before = db_counts(session)
    response = agent_client.post(
        "/api/v1/agent/jobs", json=payload(module_id="nope"), headers=headers,
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "AGENT_MODULE_UNKNOWN"
    assert db_counts(session) == before, "拒绝请求不得产生 Prompt/Job/Stage 残留"


def test_default_unreleased_rejected_without_fallback(agent_client, session, monkeypatch):
    monkeypatch.setattr(release, "load_release_manifest", lambda: {"modules": {}})
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-default-gate")
    monkeypatch.setenv(ENV_AGENT_RATE_LIMIT, "0")
    headers = {"Authorization": "Bearer test-token-default-gate"}
    before = db_counts(session)
    response = agent_client.post(
        "/api/v1/agent/jobs", json=payload(module_id=None), headers=headers,
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "WORKFLOW_NOT_RELEASED"
    assert db_counts(session) == before, "默认工作流未放行时不得自动切换或写库"


def test_non_text_module_rejected_without_side_effects(agent_client, session, monkeypatch):
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-process")
    monkeypatch.setenv(ENV_AGENT_RATE_LIMIT, "0")
    headers = {"Authorization": "Bearer test-token-process"}
    before = db_counts(session)
    response = agent_client.post(
        "/api/v1/agent/jobs", json=payload(module_id="upscale"), headers=headers,
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "AGENT_MODULE_NOT_TEXT_GENERATE"
    assert db_counts(session) == before


def test_upscale_appended_after_selected_primary(agent_client, monkeypatch):
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-upscale")
    monkeypatch.setenv(ENV_AGENT_RATE_LIMIT, "0")
    headers = {"Authorization": "Bearer test-token-upscale"}
    response = agent_client.post(
        "/api/v1/agent/jobs",
        json=payload(module_id="anime_generate", upscale=True),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    modules = response.json()["workflow_snapshot"]["modules"]
    assert [item["module_id"] for item in modules] == ["anime_generate", "upscale"]
    assert [
        item["module_id"] for item in response.json()["workbench_snapshot"]["workflow_modules"]
    ] == ["anime_generate", "upscale"]
