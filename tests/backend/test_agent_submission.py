"""Agent 提交端点（Phase 0.34）：默认关闭 / Bearer token / 限速 / 幂等 / 参数校验。"""
from __future__ import annotations

import dataclasses
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import ENV_AGENT_RATE_LIMIT, ENV_AGENT_TOKEN, Settings, WorkflowConfig
from app.engine import release
from app.main import create_app
from app.models import Job, JobStage, Prompt
from app.services import job_service


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


# ===== W1.2.1：事务 / 严格 module_id / CLI 服务端行为 =====

def test_fixed_seed_with_count_two_rolls_back_prompt_and_job(agent_client, session, monkeypatch):
    """A：count=2 + 固定 Seed 校验失败 → Prompt / Job / JobStage 均不增加。"""
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-rollback")
    monkeypatch.setenv(ENV_AGENT_RATE_LIMIT, "0")
    headers = {"Authorization": "Bearer test-token-rollback"}
    before = db_counts(session)
    response = agent_client.post(
        "/api/v1/agent/jobs",
        json=payload(count=2, seed=1234),
        headers=headers,
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "FIXED_SEED_SINGLE_ONLY"
    assert db_counts(session) == before, "校验失败必须回滚尚未提交的 Prompt"


def test_idempotency_conflict_does_not_create_prompt(agent_client, session, monkeypatch):
    """B：相同 client_request_id + 不同 Prompt → 409，且不新增 Prompt、原 Job 不变。"""
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-idem-conflict")
    monkeypatch.setenv(ENV_AGENT_RATE_LIMIT, "0")
    headers = {"Authorization": "Bearer test-token-idem-conflict"}
    request_id = f"conflict_{uuid.uuid4().hex[:10]}"
    first = agent_client.post(
        "/api/v1/agent/jobs",
        json=payload(client_request_id=request_id, prompt="first prompt"),
        headers=headers,
    )
    assert first.status_code == 201, first.text
    first_job = first.json()
    prompt_after_first = session.query(Prompt).count()

    second = agent_client.post(
        "/api/v1/agent/jobs",
        json=payload(client_request_id=request_id, prompt="different prompt"),
        headers=headers,
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    assert session.query(Prompt).count() == prompt_after_first, "冲突请求不得留下新 Prompt"
    detail = agent_client.get(f"/api/v1/jobs/{first_job['id']}").json()
    assert detail["positive_prompt_snapshot"] == "first prompt"


def test_blank_and_whitespace_module_id_rejected(agent_client, monkeypatch):
    """C：只有 None 才走默认；"" / "   " 必须拒绝，不能绕过显式选择。"""
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-blank")
    monkeypatch.setenv(ENV_AGENT_RATE_LIMIT, "0")
    headers = {"Authorization": "Bearer test-token-blank"}
    for value in ("", "   "):
        response = agent_client.post(
            "/api/v1/agent/jobs", json=payload(module_id=value), headers=headers,
        )
        assert response.status_code == 422, response.text
    unknown = agent_client.post(
        "/api/v1/agent/jobs", json=payload(module_id="unknown"), headers=headers,
    )
    assert unknown.status_code == 400
    assert unknown.json()["error"]["code"] == "AGENT_MODULE_UNKNOWN"


def test_legacy_doubao_path_attaches_prompt_server_side(agent_client, session, monkeypatch):
    """CLI 旧 /jobs 路径：服务端负责 Prompt 关联，Job 快照带 source_prompt_id。"""
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-legacy")
    monkeypatch.setenv(ENV_AGENT_RATE_LIMIT, "0")
    headers = {"Authorization": "Bearer test-token-legacy"}
    before_jobs = session.query(Job).count()
    response = agent_client.post("/api/v1/jobs", json={
        "source": "doubao",
        "client_request_id": f"legacy_{uuid.uuid4().hex[:10]}",
        "snapshot": {
            "prompt_mode": "full",
            "full_prompt": "legacy cli prompt, silver hair",
            "negative_prompt": "low quality",
            "width": 768,
            "height": 1024,
            "count": 1,
            "seed_mode": "random",
            "workflow_modules": [],
        },
    })
    assert response.status_code == 201, response.text
    job = response.json()
    snapshot = job["workbench_snapshot"]
    assert snapshot["source_prompt_id"], "服务端必须关联提示词"
    assert snapshot["source_prompt_version_id"]
    assert session.query(Job).count() == before_jobs + 1
    assert session.query(Prompt).count() == 1


def test_legacy_doubao_invalid_job_rolls_back_prompt(agent_client, session, monkeypatch):
    """CLI 旧 /jobs 路径校验失败时，服务端不得提前留下 Prompt。"""
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-legacy-fail")
    monkeypatch.setenv(ENV_AGENT_RATE_LIMIT, "0")
    before = db_counts(session)
    response = agent_client.post("/api/v1/jobs", json={
        "source": "doubao",
        "client_request_id": f"legacy_fail_{uuid.uuid4().hex[:10]}",
        "snapshot": {
            "prompt_mode": "full",
            "full_prompt": "should not persist prompt",
            "negative_prompt": "",
            "width": 768,
            "height": 1024,
            "count": 2,
            "seed_mode": "fixed",
            "seed": 42,
            "workflow_modules": [],
        },
    })
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "FIXED_SEED_SINGLE_ONLY"
    assert db_counts(session) == before


# ===== W1.2.2：Prompt 归档与幂等指纹解耦 =====

def test_replay_after_prompt_archived_returns_original_job(agent_client, session, monkeypatch):
    """B：原 Prompt 归档后，相同请求键 + 相同内容必须返回原 Job，且不新建 Prompt。"""
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-archive")
    monkeypatch.setenv(ENV_AGENT_RATE_LIMIT, "0")
    headers = {"Authorization": "Bearer test-token-archive"}
    body = payload(prompt="archive replay prompt", client_request_id=f"arch_{uuid.uuid4().hex[:10]}")
    first = agent_client.post("/api/v1/agent/jobs", json=body, headers=headers)
    assert first.status_code == 201, first.text
    job = first.json()
    prompt_id = job["workbench_snapshot"]["source_prompt_id"]
    prompt = session.get(Prompt, prompt_id)
    assert prompt is not None
    prompt.archived = True
    session.commit()
    prompt_count = session.query(Prompt).count()

    replay = agent_client.post("/api/v1/agent/jobs", json=body, headers=headers)
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == job["id"]
    assert replay.json()["idempotent_replay"] is True
    assert session.query(Prompt).count() == prompt_count, "归档不应因重放产生新 Prompt"
    detail = agent_client.get(f"/api/v1/jobs/{job['id']}").json()
    assert detail["workbench_snapshot"]["source_prompt_id"] == prompt_id


def test_legacy_fingerprint_job_replays_after_prompt_archive(agent_client, session, monkeypatch):
    """兼容 W1.2.2 之前（指纹含 Prompt 溯源）的历史 Job：重建旧指纹后仍可重放。"""
    monkeypatch.setenv(ENV_AGENT_TOKEN, "test-token-legacy-fp")
    monkeypatch.setenv(ENV_AGENT_RATE_LIMIT, "0")
    headers = {"Authorization": "Bearer test-token-legacy-fp"}
    body = payload(prompt="legacy fingerprint prompt", client_request_id=f"lfp_{uuid.uuid4().hex[:10]}")
    first = agent_client.post("/api/v1/agent/jobs", json=body, headers=headers)
    assert first.status_code == 201, first.text
    job_id = first.json()["id"]

    db_job = session.get(Job, job_id)
    stored_snapshot = json.loads(db_job.workbench_snapshot_json or "{}")
    db_job.client_request_fingerprint = job_service._request_fingerprint(
        job_kind="generate",
        snapshot=stored_snapshot,
        input_image_ids=[],
        stage_configs=[],
        include_prompt_provenance=True,
    )
    prompt_id = stored_snapshot["source_prompt_id"]
    prompt = session.get(Prompt, prompt_id)
    prompt.archived = True
    session.commit()
    prompt_count = session.query(Prompt).count()

    replay = agent_client.post("/api/v1/agent/jobs", json=body, headers=headers)
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == job_id
    assert replay.json()["idempotent_replay"] is True
    assert session.query(Prompt).count() == prompt_count
