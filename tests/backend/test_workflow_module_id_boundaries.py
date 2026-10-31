"""W1.2.2：所有入口严格拒绝空/纯空白 module_id，空列表仍使用服务器默认。"""
from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, WorkflowConfig
from app.engine.base import EngineError
from app.engine.factory import resolve_workflow_modules
from app.main import create_app
from app.models import Job, JobStage, Prompt


def mock_settings(settings: Settings) -> Settings:
    return dataclasses.replace(
        settings,
        workflow=WorkflowConfig(raw={"engine": {"provider": "mock", "options": {
            "worker_poll_interval_ms": 20, "engine_poll_ms": 20,
        }}}),
    )


@pytest.fixture()
def mock_client(settings):
    app = create_app(mock_settings(settings))
    with TestClient(app) as test_client:
        yield test_client


def snapshot(modules: list[dict]) -> dict:
    return {
        "prompt_mode": "full",
        "full_prompt": "1girl, silver hair, studio portrait",
        "negative_prompt": "blurry",
        "width": 768,
        "height": 768,
        "count": 1,
        "seed_mode": "random",
        "workflow_modules": modules,
    }


def db_counts(session) -> tuple[int, int, int]:
    return (
        session.query(Prompt).count(),
        session.query(Job).count(),
        session.query(JobStage).count(),
    )


def test_empty_module_list_uses_server_default(mock_client):
    response = mock_client.post("/api/v1/jobs", json={
        "source": "web",
        "client_request_id": "w122-empty-list",
        "snapshot": snapshot([]),
    })
    assert response.status_code == 201, response.text
    assert response.json()["module_id"] == "basic_generate"


@pytest.mark.parametrize("module_id", ["", "   "])
def test_explicit_blank_module_id_rejected_without_side_effects(mock_client, session, module_id):
    before = db_counts(session)
    response = mock_client.post("/api/v1/jobs", json={
        "source": "web",
        "client_request_id": f"w122-blank-{len(module_id)}",
        "snapshot": snapshot([{"module_id": module_id}]),
    })
    assert response.status_code == 422, response.text
    assert db_counts(session) == before, "拒绝请求不得产生 Prompt / Job / JobStage"


def test_factory_rejects_blank_module_id_directly(settings):
    """service/factory 层二次防护：不能只依赖 Pydantic。"""
    with pytest.raises(EngineError) as exc:
        resolve_workflow_modules(mock_settings(settings), [{"module_id": "   "}])
    assert exc.value.error_type == "MODULE_ID_INVALID"


def test_factory_still_allows_truly_empty_request(settings):
    identity = resolve_workflow_modules(mock_settings(settings), [])[0]
    assert identity["module_id"] == "basic_generate"
