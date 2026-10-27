"""AI 提交前的提示词入库保证（assign_ai_prompt / POST /prompts/ensure）。

基础可追溯要求：AI 提交的每段提示词必须先入提示词库，Job 快照带 source_prompt_id，
生成图才能在提示词库按提示词查到；同文重复提交不得堆出重复条目。
"""
from __future__ import annotations

import pytest

from app.core.errors import ValidationError
from app.services import prompt_service


def test_assign_ai_prompt_creates_then_reuses(session):
    prompt, version, created = prompt_service.assign_ai_prompt(
        session, positive_prompt="1girl, red dress", negative_prompt="blur"
    )
    assert created is True
    assert prompt.id.startswith("prm_") and version.id.startswith("prmv_")
    assert version.mode == "full"
    assert version.negative_prompt == "blur"

    again, version_again, created_again = prompt_service.assign_ai_prompt(
        session, positive_prompt="1girl, red dress", negative_prompt="blur"
    )
    assert created_again is False
    assert again.id == prompt.id
    assert version_again.id == version.id


def test_assign_ai_prompt_different_negative_creates_new_entry(session):
    first, _, _ = prompt_service.assign_ai_prompt(
        session, positive_prompt="same text", negative_prompt="blur"
    )
    second, _, created = prompt_service.assign_ai_prompt(
        session, positive_prompt="same text", negative_prompt="lowres"
    )
    assert created is True
    assert second.id != first.id


def test_assign_ai_prompt_rejects_empty(session):
    with pytest.raises(ValidationError):
        prompt_service.assign_ai_prompt(session, positive_prompt="   ")


def test_ensure_endpoint_is_idempotent(client):
    payload = {"positive_prompt": "ensure-endpoint prompt", "negative_prompt": "blur"}
    first = client.post("/api/v1/prompts/ensure", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["created"] is True
    second = client.post("/api/v1/prompts/ensure", json=payload)
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["created"] is False
    assert body["prompt_id"] == first.json()["prompt_id"]

    images = client.get(f"/api/v1/prompts/{body['prompt_id']}/images")
    assert images.status_code == 200
