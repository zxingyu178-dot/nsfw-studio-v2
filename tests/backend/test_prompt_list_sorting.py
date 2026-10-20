"""Prompt 列表状态筛选、最新评分排序与稳定分页。"""
import pytest
from sqlalchemy import text


def _prompt(client, name: str):
    response = client.post("/api/v1/prompts", json={"name": name, "mode": "full"})
    assert response.status_code == 201
    return response.json()


def _evaluate(client, prompt_id: str, score: int):
    response = client.post(
        f"/api/v1/prompts/{prompt_id}/evaluations",
        json={"overall_score": score, "dimension_scores": {}},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize("status", ["keep", "candidate", "eliminated"])
def test_status_filter_returns_only_matching_prompts(client, status):
    prompts = {value: _prompt(client, value) for value in ("keep", "candidate", "eliminated")}
    for value in ("keep", "eliminated"):
        response = client.post(
            f"/api/v1/prompts/{prompts[value]['id']}/status",
            json={"status": value},
        )
        assert response.status_code == 200

    response = client.get("/api/v1/prompts", params={"status": status})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [prompts[status]["id"]]
    assert all(item["status"] == status for item in body["items"])


def test_score_sort_uses_latest_evaluation_and_puts_unscored_last(client):
    high = _prompt(client, "high")
    medium = _prompt(client, "medium")
    latest_low = _prompt(client, "latest-low")
    unscored = _prompt(client, "unscored")
    _evaluate(client, high["id"], 5)
    _evaluate(client, medium["id"], 3)
    old = _evaluate(client, latest_low["id"], 5)
    new = _evaluate(client, latest_low["id"], 1)
    with client.app.state.session_factory() as session:
        session.execute(
            text("UPDATE prompt_evaluations SET created_at=:created_at WHERE id=:id"),
            {"created_at": "2026-10-20T01:00:00.000Z", "id": old["id"]},
        )
        session.execute(
            text("UPDATE prompt_evaluations SET created_at=:created_at WHERE id=:id"),
            {"created_at": "2026-10-20T02:00:00.000Z", "id": new["id"]},
        )
        session.commit()

    descending = client.get("/api/v1/prompts", params={"sort": "score_desc"})
    ascending = client.get("/api/v1/prompts", params={"sort": "score_asc"})

    assert descending.status_code == 200
    assert ascending.status_code == 200
    assert [item["id"] for item in descending.json()["items"]] == [
        high["id"], medium["id"], latest_low["id"], unscored["id"],
    ]
    assert [item["id"] for item in ascending.json()["items"]] == [
        latest_low["id"], medium["id"], high["id"], unscored["id"],
    ]


@pytest.mark.parametrize("parameter,value", [("sort", "newest"), ("status", "automatic")])
def test_invalid_list_enum_returns_422(client, parameter, value):
    response = client.get("/api/v1/prompts", params={parameter: value})

    assert response.status_code == 422


def test_score_sort_limit_offset_is_stable(client):
    prompts = [_prompt(client, f"prompt-{index}") for index in range(5)]
    with client.app.state.session_factory() as session:
        session.execute(text("UPDATE prompts SET updated_at='2026-10-20T01:00:00.000Z'"))
        session.commit()
    expected = sorted((prompt["id"] for prompt in prompts), reverse=True)

    first = client.get("/api/v1/prompts", params={"sort": "score_desc", "limit": 2})
    second = client.get(
        "/api/v1/prompts", params={"sort": "score_desc", "limit": 2, "offset": 2},
    )
    third = client.get(
        "/api/v1/prompts", params={"sort": "score_desc", "limit": 2, "offset": 4},
    )

    assert first.status_code == second.status_code == third.status_code == 200
    first_ids = [item["id"] for item in first.json()["items"]]
    second_ids = [item["id"] for item in second.json()["items"]]
    third_ids = [item["id"] for item in third.json()["items"]]
    assert first_ids == expected[:2]
    assert second_ids == expected[2:4]
    assert third_ids == expected[4:]
    assert set(first_ids).isdisjoint(second_ids)
