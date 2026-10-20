"""Prompt 列表多状态与评分存在性筛选契约。"""
import pytest
from sqlalchemy import text


def _prompt(client, name: str):
    response = client.post("/api/v1/prompts", json={"name": name, "mode": "full"})
    assert response.status_code == 201
    return response.json()


def _set_status(client, prompt_id: str, status: str):
    response = client.post(
        f"/api/v1/prompts/{prompt_id}/status",
        json={"status": status},
    )
    assert response.status_code == 200


def _evaluate(client, prompt_id: str, score: int = 3):
    response = client.post(
        f"/api/v1/prompts/{prompt_id}/evaluations",
        json={"overall_score": score, "dimension_scores": {}},
    )
    assert response.status_code == 201


def test_repeated_status_filters_return_union_without_other_statuses(client):
    keep = _prompt(client, "keep")
    candidate = _prompt(client, "candidate")
    eliminated = _prompt(client, "eliminated")
    _set_status(client, keep["id"], "keep")
    _set_status(client, eliminated["id"], "eliminated")

    response = client.get(
        "/api/v1/prompts",
        params=[("status", "keep"), ("status", "candidate")],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["id"] for item in body["items"]} == {keep["id"], candidate["id"]}
    assert {item["status"] for item in body["items"]} == {"keep", "candidate"}
    assert eliminated["id"] not in {item["id"] for item in body["items"]}


@pytest.mark.parametrize(
    ("scored", "expected_name"),
    [(True, "scored"), (False, "unscored")],
)
def test_scored_filter_selects_prompts_by_evaluation_existence(client, scored, expected_name):
    prompts = {
        name: _prompt(client, name)
        for name in ("scored", "unscored")
    }
    _evaluate(client, prompts["scored"]["id"])

    response = client.get("/api/v1/prompts", params={"scored": scored})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [prompts[expected_name]["id"]]


def test_scored_and_status_filters_are_combined(client):
    keep_scored = _prompt(client, "keep-scored")
    keep_unscored = _prompt(client, "keep-unscored")
    candidate_scored = _prompt(client, "candidate-scored")
    _set_status(client, keep_scored["id"], "keep")
    _set_status(client, keep_unscored["id"], "keep")
    _evaluate(client, keep_scored["id"])
    _evaluate(client, candidate_scored["id"])

    response = client.get(
        "/api/v1/prompts",
        params=[("scored", "true"), ("status", "keep")],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [keep_scored["id"]]


def test_single_invalid_status_returns_422(client):
    response = client.get("/api/v1/prompts", params={"status": "automatic"})

    assert response.status_code == 422


def test_repeated_status_with_one_invalid_value_returns_422(client):
    response = client.get(
        "/api/v1/prompts",
        params=[("status", "automatic"), ("status", "keep")],
    )

    assert response.status_code == 422


def test_score_desc_with_unscored_filter_falls_back_to_updated_desc(client):
    oldest = _prompt(client, "oldest")
    newest = _prompt(client, "newest")
    middle = _prompt(client, "middle")
    scored = _prompt(client, "scored")
    _evaluate(client, scored["id"], score=5)
    timestamps = {
        oldest["id"]: "2026-10-20T01:00:00.000Z",
        middle["id"]: "2026-10-20T02:00:00.000Z",
        newest["id"]: "2026-10-20T03:00:00.000Z",
        scored["id"]: "2026-10-20T04:00:00.000Z",
    }
    with client.app.state.session_factory() as session:
        for prompt_id, updated_at in timestamps.items():
            session.execute(
                text("UPDATE prompts SET updated_at=:updated_at WHERE id=:id"),
                {"updated_at": updated_at, "id": prompt_id},
            )
        session.commit()

    response = client.get(
        "/api/v1/prompts",
        params={"sort": "score_desc", "scored": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == [
        newest["id"], middle["id"], oldest["id"],
    ]
