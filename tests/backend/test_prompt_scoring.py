"""手动评分、淘汰状态与批量最新评分契约。"""
import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError

from app.database.base import init_database
from app.database import migrations


def _prompt(client, name="评分测试"):
    response = client.post("/api/v1/prompts", json={"name": name, "mode": "full"})
    assert response.status_code == 201
    return response.json()


def _evaluate(client, prompt, **fields):
    return client.post(f"/api/v1/prompts/{prompt['id']}/evaluations", json={
        "overall_score": 4, "dimension_scores": {}, **fields,
    })


def test_create_evaluation(client):
    prompt = _prompt(client)
    dimensions = dict.fromkeys(("subject", "clothing", "scene", "composition", "lighting", "style", "quality"), 5)
    response = _evaluate(client, prompt, dimension_scores=dimensions, notes="光影自然",
                         prompt_version_id=prompt["current_version"]["id"])
    assert response.status_code == 201
    body = response.json()
    assert body["id"].startswith("prev_")
    assert body["prompt_id"] == prompt["id"]
    assert body["prompt_version_id"] == prompt["current_version"]["id"]
    assert body["overall_score"] == 4
    assert body["dimension_scores"] == dimensions
    assert body["source"] == "user"
    assert body["notes"] == "光影自然"
    assert body["created_at"].endswith("Z")
    assert client.get(f"/api/v1/prompts/{prompt['id']}/evaluations").json() == [body]


@pytest.mark.parametrize("fields", [
    {"dimension_scores": {"unknown": 3}}, {"overall_score": 0}, {"overall_score": 6},
    {"dimension_scores": {"quality": 0}}, {"dimension_scores": {"quality": 6}},
    {"overall_score": 1.5}, {"overall_score": True},
])
def test_invalid_evaluation(client, fields):
    prompt = _prompt(client)
    response = _evaluate(client, prompt, **fields)
    assert response.status_code == 422
    assert "error" in response.json()
    assert client.get(f"/api/v1/prompts/{prompt['id']}/evaluations").json() == []


def test_evaluations_order_and_isolation(client):
    prompt, other = _prompt(client), _prompt(client, "其他")
    assert client.get(f"/api/v1/prompts/{prompt['id']}/evaluations").json() == []
    ids = []
    for timestamp in ("2026-10-20T01:00:00.000Z", "2026-10-20T03:00:00.000Z", "2026-10-20T02:00:00.000Z"):
        response = _evaluate(client, prompt)
        assert response.status_code == 201
        evaluation = response.json()
        assert evaluation["prompt_version_id"] is None
        assert evaluation["notes"] == ""
        ids.append(evaluation["id"])
        with client.app.state.session_factory() as session:
            session.execute(text("UPDATE prompt_evaluations SET created_at=:time WHERE id=:id"),
                            {"time": timestamp, "id": evaluation["id"]})
            session.commit()
    _evaluate(client, other)
    body = client.get(f"/api/v1/prompts/{prompt['id']}/evaluations").json()
    assert [item["id"] for item in body] == [ids[1], ids[2], ids[0]]


@pytest.mark.parametrize("method,suffix,body", [
    ("post", "evaluations", {"overall_score": 3, "dimension_scores": {}}),
    ("get", "evaluations", None), ("post", "status", {"status": "keep"}),
])
def test_missing_prompt(client, method, suffix, body):
    response = client.request(method, f"/api/v1/prompts/prm_missing/{suffix}", **({"json": body} if body else {}))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROMPT_NOT_FOUND"


def test_missing_or_foreign_version(client):
    prompt, other = _prompt(client), _prompt(client, "其他")
    for version_id in ("prmv_missing", other["current_version"]["id"]):
        response = _evaluate(client, prompt, prompt_version_id=version_id)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PROMPT_VERSION_NOT_FOUND"
    assert client.get(f"/api/v1/prompts/{prompt['id']}/evaluations").json() == []


@pytest.mark.parametrize("status", ["keep", "candidate", "eliminated"])
def test_manual_status_persists_without_new_version(client, status):
    prompt = _prompt(client)
    assert prompt["status"] == "candidate" and prompt["status_reason"] == ""
    response = client.post(f"/api/v1/prompts/{prompt['id']}/status", json={"status": status, "reason": "人工判断"})
    assert response.status_code == 200
    for body in (response.json(), client.get(f"/api/v1/prompts/{prompt['id']}").json()):
        assert body["status"] == status
        assert body["status_reason"] == "人工判断"
        assert body["current_version"] == prompt["current_version"]
        assert body["archived"] is False
    assert len(client.get(f"/api/v1/prompts/{prompt['id']}/versions").json()) == 1
    _evaluate(client, prompt, overall_score=1)
    assert client.get(f"/api/v1/prompts/{prompt['id']}").json()["status"] == status
    reset = client.post(f"/api/v1/prompts/{prompt['id']}/status", json={"status": "candidate"})
    assert reset.json()["status_reason"] == ""


def test_invalid_status(client):
    prompt = _prompt(client)
    response = client.post(f"/api/v1/prompts/{prompt['id']}/status", json={"status": "automatic"})
    assert response.status_code == 422
    assert "error" in response.json()


def test_list_latest_evaluation_fixed_queries(client):
    first, second, empty = [_prompt(client, name) for name in ("甲", "乙", "空")]
    evaluations = [_evaluate(client, first, overall_score=score).json() for score in (2, 5)]
    other = _evaluate(client, second).json()
    # 同一毫秒以 ID 降序稳定打破平局，列表与历史使用相同规则。
    with client.app.state.session_factory() as session:
        session.execute(text("UPDATE prompt_evaluations SET created_at='2026-10-20T01:00:00.000Z'"))
        session.commit()
    expected = max(evaluations, key=lambda item: item["id"])
    statements = []
    engine = client.app.state.session_factory.kw["bind"]

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and any(
            table in statement for table in ("prompts", "prompt_versions", "prompt_evaluations")
        ):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        for limit in (1, 50):
            statements.clear()
            response = client.get("/api/v1/prompts", params={"include_evaluation": True, "limit": limit})
            assert response.status_code == 200
            assert len(statements) == 4  # 总数、提示词、版本、评分各一次。
        items = {item["id"]: item for item in response.json()["items"]}
        statements.clear()
        default = client.get("/api/v1/prompts").json()
        assert len(statements) == 3
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert items[first["id"]]["latest_evaluation"]["id"] == expected["id"]
    assert items[second["id"]]["latest_evaluation"]["id"] == other["id"]
    assert items[empty["id"]]["latest_evaluation"] is None
    assert all("latest_evaluation" not in item for item in default["items"])
    assert all(item["status"] == "candidate" and item["status_reason"] == "" for item in items.values())
    history = client.get(f"/api/v1/prompts/{first['id']}/evaluations").json()
    assert history[0]["id"] == expected["id"]
    combined = client.get("/api/v1/prompts", params={"include_evaluation": True, "include_images": True}).json()
    assert all(item["images"] == [] and "latest_evaluation" in item for item in combined["items"])
    assert client.get("/api/v1/prompts", params={"include_evaluation": True, "offset": 100}).json()["items"] == []


def test_migration_repeat_start(client):
    engine = client.app.state.session_factory.kw["bind"]
    assert init_database(engine) == []
    assert init_database(engine) == []
    prompt = _prompt(client)
    assert _evaluate(client, prompt).status_code == 201


def test_migration_existing_rows_and_constraints(monkeypatch):
    """真实执行旧迁移再升级；内存数据库只用于此迁移单元测试。"""
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", lambda conn, record: conn.execute("PRAGMA foreign_keys=ON"))
    all_migrations = migrations.MIGRATIONS
    try:
        with monkeypatch.context() as patch:
            patch.setattr(migrations, "MIGRATIONS", all_migrations[:-2])
            init_database(engine)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO prompts (id, name, created_at, updated_at) "
                              "VALUES ('prm_legacy', '历史提示词', '2026-01-01', '2026-01-01')"))
        assert [item.migration_id for item in init_database(engine)] == [
            "0019_prompt_scoring", "0020_review_session_end_reason",
        ]
        assert init_database(engine) == []
        with engine.connect() as conn:
            assert conn.execute(text("SELECT status, status_reason FROM prompts")).one() == ("candidate", "")
        indexes = {index["column_names"][0] for index in inspect(engine).get_indexes("prompt_evaluations")}
        assert indexes == {"prompt_id", "created_at"}
        for score in (0, 6):
            with pytest.raises(IntegrityError), engine.begin() as conn:
                conn.execute(text("INSERT INTO prompt_evaluations (id, prompt_id, overall_score, created_at) "
                                  "VALUES ('prev_bad', 'prm_legacy', :score, '2026-01-01')"), {"score": score})
        for prompt_id, version_id in (("prm_missing", None), ("prm_legacy", "prmv_missing")):
            with pytest.raises(IntegrityError), engine.begin() as conn:
                conn.execute(text("INSERT INTO prompt_evaluations "
                                  "(id, prompt_id, prompt_version_id, overall_score, created_at) "
                                  "VALUES ('prev_bad', :prompt, :version, 3, '2026-01-01')"),
                             {"prompt": prompt_id, "version": version_id})
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO prompt_evaluations (id, prompt_id, overall_score, created_at) "
                              "VALUES ('prev_ok', 'prm_legacy', 3, '2026-01-01')"))
            assert conn.execute(text("SELECT dimension_scores_json, source, notes FROM prompt_evaluations")).one() == (
                "{}", "user", "",
            )
    finally:
        engine.dispose()
