"""提示词生成图片的只读聚合、分页及批量查询契约。"""
import json

import pytest
from sqlalchemy import event

from app.core.ids import IMAGE, JOB, new_id
from app.models import Image, Job


def _prompt(client, name="图片测试"):
    response = client.post("/api/v1/prompts", json={"name": name, "mode": "full", "positive_prompt": name})
    assert response.status_code == 201
    return response.json()


def _images(client, prompt, times, version_id=None):
    with client.app.state.session_factory() as session:
        job = Job(
            id=new_id(JOB), source="web", status="COMPLETED", prompt_mode="full",
            workbench_snapshot_json=json.dumps({
                "source_prompt_id": prompt["id"],
                "source_prompt_version_id": version_id or prompt["current_version"]["id"],
            }), generation_settings_json="{}", requested_count=len(times), module_id="basic_generate",
        )
        session.add(job)
        session.flush()
        ids = []
        for timestamp in times:
            image_id = new_id(IMAGE)
            session.add(Image(id=image_id, job_id=job.id, file_path=f"images/{image_id}.png",
                              width=640, height=480, source="mock", created_at=timestamp))
            ids.append(image_id)
        session.commit()
        return ids


def test_prompt_images_empty(client):
    prompt = _prompt(client)
    response = client.get(f"/api/v1/prompts/{prompt['id']}/images")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


def test_prompt_images_sorted_and_paginated(client):
    prompt = _prompt(client)
    ids = _images(client, prompt, ["2026-10-20T01:00:00Z", "2026-10-20T03:00:00Z", "2026-10-20T02:00:00Z"])
    url = f"/api/v1/prompts/{prompt['id']}/images"
    body = client.get(url).json()
    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == [ids[1], ids[2], ids[0]]
    image = body["items"][0]
    assert image["job_status"] == "COMPLETED"
    assert image["module_id"] == "basic_generate"
    assert (image["width"], image["height"]) == (640, 480)
    assert image["thumbnail_url"] == f"/api/v1/images/{ids[1]}/thumbnail"
    assert image["preview_url"] == f"/api/v1/images/{ids[1]}/preview"
    page = client.get(url, params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 3
    assert [item["id"] for item in page["items"]] == [ids[2]]
    assert client.get(url, params={"offset": 20}).json()["total"] == 3


def test_prompt_images_version_filter(client):
    prompt = _prompt(client)
    first = _images(client, prompt, ["2026-10-20T01:00:00Z"])
    version = client.post(f"/api/v1/prompts/{prompt['id']}/versions", json={
        "mode": "full", "positive_prompt": "新版",
    }).json()
    second = _images(client, prompt, ["2026-10-20T02:00:00Z"], version["id"])
    url = f"/api/v1/prompts/{prompt['id']}/images"
    assert client.get(url).json()["total"] == 2
    for version_id, ids in [(prompt["current_version"]["id"], first), (version["id"], second)]:
        body = client.get(url, params={"version_id": version_id}).json()
        assert body["total"] == 1
        assert [item["id"] for item in body["items"]] == ids


def test_prompt_list_batch_images_and_query_count(client):
    first, second, empty = [_prompt(client, name) for name in ("甲", "乙", "空")]
    ids = _images(client, first, ["2026-10-20T01:00:00Z", "2026-10-20T03:00:00Z", "2026-10-20T02:00:00Z"])
    other = _images(client, second, ["2026-10-20T04:00:00Z"])
    statements = []
    engine = client.app.state.session_factory.kw["bind"]

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and any(
            table in statement for table in ("prompts", "prompt_versions", "images")
        ):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        for limit in (1, 50):
            statements.clear()
            response = client.get("/api/v1/prompts", params={"include_images": True, "images_limit": 2, "limit": limit})
            assert response.status_code == 200
            assert len(statements) == 4  # 总数、列表、当前版本、图片窗口聚合，均与提示词数量无关。
        items = {item["id"]: item for item in response.json()["items"]}
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert items[first["id"]]["images_total"] == 3
    assert [item["id"] for item in items[first["id"]]["images"]] == [ids[1], ids[2]]
    assert items[second["id"]]["images_total"] == 1
    assert [item["id"] for item in items[second["id"]]["images"]] == other
    assert items[empty["id"]]["images_total"] == 0
    assert items[empty["id"]]["images"] == []
    default = client.get("/api/v1/prompts").json()
    assert all("images" not in item and "images_total" not in item for item in default["items"])


def test_prompt_images_not_found(client):
    prompt, other = _prompt(client), _prompt(client, "其他")
    response = client.get("/api/v1/prompts/prm_missing/images")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROMPT_NOT_FOUND"
    for version_id in ("pv_missing", other["current_version"]["id"]):
        response = client.get(f"/api/v1/prompts/{prompt['id']}/images", params={"version_id": version_id})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PROMPT_VERSION_NOT_FOUND"


@pytest.mark.parametrize("query", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
def test_prompt_images_invalid_pagination(client, query):
    prompt = _prompt(client)
    assert client.get(f"/api/v1/prompts/{prompt['id']}/images", params=query).status_code == 422


@pytest.mark.parametrize("limit", [0, 11])
def test_prompt_list_invalid_images_limit(client, limit):
    assert client.get("/api/v1/prompts", params={"images_limit": limit}).status_code == 422


def test_prompt_images_excludes_unattributed_and_other_prompts(client):
    prompt, other = _prompt(client), _prompt(client, "无关")
    expected = _images(client, prompt, ["2026-10-20T01:00:00Z", "2026-10-20T01:00:00Z"])
    _images(client, other, ["2026-10-20T03:00:00Z"])
    legacy = _images(client, prompt, ["2026-10-20T04:00:00Z"])[0]
    with client.app.state.session_factory() as session:
        image = session.get(Image, legacy)
        session.get(Job, image.job_id).workbench_snapshot_json = "{}"
        session.add(Image(id=new_id(IMAGE), file_path="imports/external.png", width=1, height=1, source="import"))
        session.get(Image, expected[0]).metadata_json = json.dumps({"module_id": "upscale"})
        session.commit()
    body = client.get(f"/api/v1/prompts/{prompt['id']}/images").json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == sorted(expected, reverse=True)
    assert next(item for item in body["items"] if item["id"] == expected[0])["module_id"] == "upscale"
