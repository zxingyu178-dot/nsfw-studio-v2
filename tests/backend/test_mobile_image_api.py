"""Mobile 图片内容端点 + 缓存头测试（thumbnail/preview/original，Bearer）。"""
from __future__ import annotations


def _auth(mobile_client, session_factory):
    from app.services import mobile_pairing_service
    with session_factory() as session:
        code = mobile_pairing_service.generate_pairing_code(session)
    r = mobile_client.post("/mobile/pairing/verify", json={
        "installation_id": "dev-img", "device_name": "p", "code": code,
    })
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _new_session(mobile_client, h):
    return mobile_client.post("/mobile/review/sessions", json={}, headers=h).json()["data"]["id"]


def test_image_content_requires_bearer(mobile_client, make_mobile_image):
    imgs = make_mobile_image(1)
    r = mobile_client.get(f"/mobile/images/{imgs[0].id}/thumbnail")
    assert r.status_code == 401


def test_thumbnail_preview_original_and_headers(mobile_client, session_factory, make_mobile_image):
    imgs = make_mobile_image(1)
    h = _auth(mobile_client, session_factory)
    sid = _new_session(mobile_client, h)
    q = mobile_client.get(f"/mobile/review/sessions/{sid}/queue", headers=h).json()["data"]["items"]
    image_id = q[0]["image"]["image_id"]

    thumb = mobile_client.get(f"/mobile/images/{image_id}/thumbnail", headers=h)
    assert thumb.status_code == 200
    assert thumb.headers["X-Content-Type-Options"] == "nosniff"
    assert "private" in thumb.headers["Cache-Control"]
    assert thumb.headers.get("ETag")

    preview = mobile_client.get(f"/mobile/images/{image_id}/preview", headers=h)
    assert preview.status_code == 200
    assert preview.headers["X-Content-Type-Options"] == "nosniff"

    original = mobile_client.get(f"/mobile/images/{image_id}/original", headers=h)
    assert original.status_code == 200
    assert original.headers["X-Content-Type-Options"] == "nosniff"


def test_image_summary_dto_no_paths(mobile_client, session_factory, make_mobile_image):
    make_mobile_image(1)
    h = _auth(mobile_client, session_factory)
    sid = _new_session(mobile_client, h)
    q = mobile_client.get(f"/mobile/review/sessions/{sid}/queue", headers=h).json()["data"]["items"]
    img = q[0]["image"]
    # 必需字段
    for key in ("image_id", "width", "height", "created_at", "status", "is_favorite",
                "kind", "job_id", "seed", "thumbnail_url", "preview_url", "original_url"):
        assert key in img
    # 不下发任何路径/敏感字段
    blob = str(img)
    assert "DataRoot" not in blob
    assert "file_path" not in img
    assert "backend" not in img.get("thumbnail_url", "")
