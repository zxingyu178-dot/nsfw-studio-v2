"""Agent 提交端点（Phase 0.34）：默认关闭 / Bearer token / 限速 / 幂等 / 参数校验。"""
from __future__ import annotations

import dataclasses
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import ENV_AGENT_RATE_LIMIT, ENV_AGENT_TOKEN, Settings, WorkflowConfig
from app.engine import release
from app.main import create_app


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
    assert bad_module.status_code == 422
