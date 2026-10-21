"""GET /api/v1/images/ids：按图库筛选返回全部匹配图片 ID。"""
from __future__ import annotations

import pytest

from app.models import Image
from app.services import image_service


@pytest.fixture()
def image_ids(client) -> dict[str, str]:
    rows = [
        Image(
            id="img_import_new",
            file_path="images/originals/img_import_new/a.png",
            width=100,
            height=100,
            source="import",
            status="NEW",
            review_status="UNREVIEWED",
            created_at="2026-10-22T01:00:00+00:00",
            updated_at="2026-10-22T01:00:00+00:00",
        ),
        Image(
            id="img_import_archived",
            file_path="images/originals/img_import_archived/b.png",
            width=200,
            height=100,
            source="import",
            status="ARCHIVED",
            review_status="KEPT",
            created_at="2026-10-22T02:00:00+00:00",
            updated_at="2026-10-22T02:00:00+00:00",
        ),
        Image(
            id="img_comfyui_new",
            file_path="images/originals/img_comfyui_new/c.png",
            width=300,
            height=100,
            source="comfyui",
            status="NEW",
            review_status="UNREVIEWED",
            created_at="2026-10-22T03:00:00+00:00",
            updated_at="2026-10-22T03:00:00+00:00",
        ),
    ]
    with client.app.state.session_factory() as session:
        session.add_all(rows)
        session.commit()
    return {row.id: row.id for row in rows}


def test_ids_filters_by_source_and_matches_list_total(client, image_ids):
    response = client.get("/api/v1/images/ids", params={"source": "import"})
    listed = client.get("/api/v1/images", params={"source": "import"}).json()

    assert response.status_code == 200
    body = response.json()
    assert body["ids"] == [image_ids["img_import_archived"], image_ids["img_import_new"]]
    assert body["total"] == listed["total"] == 2
    assert body["truncated"] is False
    assert body["limit"] == 10_000


def test_ids_status_filter_matches_list_id_set(client, image_ids):
    body = client.get("/api/v1/images/ids", params={"status": "NEW"}).json()
    listed = client.get("/api/v1/images", params={"status": "NEW"}).json()

    assert set(body["ids"]) == {item["id"] for item in listed["items"]}
    assert body["total"] == listed["total"] == 2


def test_ids_empty_result(client, image_ids):
    response = client.get("/api/v1/images/ids", params={"source": "engine"})

    assert response.status_code == 200
    assert response.json() == {"ids": [], "total": 0, "truncated": False, "limit": 10_000}


def test_ids_static_route_is_not_captured_as_image_id(client, image_ids):
    response = client.get("/api/v1/images/ids")

    assert response.status_code == 200
    assert set(response.json()) == {"ids", "total", "truncated", "limit"}


def test_ids_reports_truncation_at_configured_limit(client, image_ids, monkeypatch):
    monkeypatch.setattr(image_service, "IMAGE_IDS_LIMIT", 1)

    response = client.get("/api/v1/images/ids")

    assert response.status_code == 200
    assert response.json() == {
        "ids": [image_ids["img_comfyui_new"]],
        "total": 3,
        "truncated": True,
        "limit": 1,
    }
