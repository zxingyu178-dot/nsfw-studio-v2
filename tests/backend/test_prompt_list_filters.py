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


def _evaluate(client, prompt_id: str, score: int = 3, dimension_scores: dict | None = None):
    response = client.post(
        f"/api/v1/prompts/{prompt_id}/evaluations",
        json={"overall_score": score, "dimension_scores": dimension_scores or {}},
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


def test_min_score_filter_uses_latest_evaluation_only(client):
    high = _prompt(client, "high")
    low = _prompt(client, "low")
    unscored = _prompt(client, "unscored")
    _evaluate(client, high["id"], score=5)
    _evaluate(client, low["id"], score=2)

    response = client.get("/api/v1/prompts", params={"min_score": 4})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [high["id"]]

    # 重新评分后应以“最新一条”为准：high 从 5 分降到 1 分，不再命中 ≥4。
    _evaluate(client, high["id"], score=1)

    response = client.get("/api/v1/prompts", params={"min_score": 4})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert unscored["id"] not in {item["id"] for item in body["items"]}


def test_dimension_min_score_filter_uses_latest_evaluation_dimension(client):
    strong_scene = _prompt(client, "strong-scene")
    weak_scene = _prompt(client, "weak-scene")
    no_dimension = _prompt(client, "no-dimension")
    _evaluate(client, strong_scene["id"], score=3, dimension_scores={"scene": 5})
    _evaluate(client, weak_scene["id"], score=5, dimension_scores={"scene": 2})
    _evaluate(client, no_dimension["id"], score=5)

    response = client.get(
        "/api/v1/prompts",
        params={"dimension": "scene", "min_dimension_score": 4},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [strong_scene["id"]]


def test_dimension_filter_requires_min_dimension_score(client):
    prompt = _prompt(client, "with-dimension")
    _evaluate(client, prompt["id"], score=4, dimension_scores={"style": 4})

    response = client.get("/api/v1/prompts", params={"dimension": "style"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PROMPT_DIMENSION_SCORE_MISSING"


def test_invalid_dimension_returns_422(client):
    response = client.get(
        "/api/v1/prompts",
        params={"dimension": "unknown", "min_dimension_score": 3},
    )

    assert response.status_code == 422
