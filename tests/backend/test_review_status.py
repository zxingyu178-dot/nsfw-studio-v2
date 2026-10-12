"""Phase 0.11 图片审核状态流转测试（PATCH /status + POST /batch-status）。"""
from __future__ import annotations

import pytest

from app.core.errors import ValidationError
from app.models import Image
from app.services import image_service


def _import_one(client, png_bytes):
    from app.storage.manager import StorageManager

    storage = StorageManager(client.app.state.settings)
    with client.app.state.session_factory() as session:
        image = image_service.import_engine_output(
            session, storage, data=png_bytes, original_filename="a.png", source="comfyui",
        )
        return image.id


def test_import_defaults_to_new(client, png_bytes):
    image_id = _import_one(client, png_bytes)
    with client.app.state.session_factory() as session:
        image = session.get(Image, image_id)
        assert image.status == "NEW"
        assert image.reviewed_at is None
        assert image.review_note == ""


def test_patch_status_sets_fields(client, png_bytes):
    image_id = _import_one(client, png_bytes)
    resp = client.patch(
        f"/api/v1/images/{image_id}/status", json={"status": "KEEP", "note": "不错"}
    ).json()
    assert resp["status"] == "KEEP"
    assert resp["review_note"] == "不错"
    assert resp["reviewed_at"] is not None

    with client.app.state.session_factory() as session:
        image = session.get(Image, image_id)
        assert image.status == "KEEP"
        assert image.reviewed_at is not None


def test_favorite_independent_of_status(client, png_bytes):
    """Phase 0.11.1：收藏与审核状态相互独立——set status 不再触碰 favorite；
    FAVORITE 作为审核状态写入被拒绝（收藏请走 favorite）。"""
    image_id = _import_one(client, png_bytes)

    # 收藏：只写 favorite，审核状态仍为 NEW
    fav = client.patch(f"/api/v1/images/{image_id}/favorite", json={"favorite": True}).json()
    assert fav["favorite"] is True
    assert fav["status"] == "NEW", "收藏不应改变审核状态"
    assert fav["review_status"] == "UNREVIEWED"

    # 置 KEEP：favorite 保持，且新 status=KEEP 与旧 review_status=KEPT 同源双写
    keep = client.patch(f"/api/v1/images/{image_id}/status", json={"status": "KEEP"}).json()
    assert keep["status"] == "KEEP"
    assert keep["review_status"] == "KEPT"
    assert keep["favorite"] is True, "置 KEEP 不得清除收藏"

    # FAVORITE 作为审核状态写入 → 400 IMAGE_STATUS_DEPRECATED
    resp = client.patch(f"/api/v1/images/{image_id}/status", json={"status": "FAVORITE"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "IMAGE_STATUS_DEPRECATED"


def test_back_to_new_clears_reviewed_at(client, png_bytes):
    image_id = _import_one(client, png_bytes)
    client.patch(f"/api/v1/images/{image_id}/status", json={"status": "KEEP"})
    back = client.patch(f"/api/v1/images/{image_id}/status", json={"status": "NEW"}).json()
    assert back["status"] == "NEW"
    assert back["reviewed_at"] is None


def test_invalid_status_rejected(client, png_bytes):
    image_id = _import_one(client, png_bytes)
    resp = client.patch(f"/api/v1/images/{image_id}/status", json={"status": "MAYBE"})
    assert resp.status_code in (400, 422)


def test_batch_status(client, png_bytes):
    ids = [_import_one(client, png_bytes) for _ in range(5)]
    resp = client.post("/api/v1/images/batch-status",
                       json={"image_ids": ids, "status": "REJECT", "note": "废片"}).json()
    assert resp["updated"] == 5
    assert {item["id"] for item in resp["items"]} == set(ids)

    reject_count = client.get("/api/v1/images", params={"status": "REJECT"}).json()["total"]
    assert reject_count == 5


def test_batch_invalid_status_rejected(client, png_bytes):
    ids = [_import_one(client, png_bytes)]
    resp = client.post("/api/v1/images/batch-status",
                       json={"image_ids": ids, "status": "GOLD"})
    assert resp.status_code in (400, 422)


def test_service_set_image_status_directly(session, settings, png_bytes):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = image_service.import_engine_output(
        session, storage, data=png_bytes, original_filename="a.png", source="comfyui",
    )
    image_service.set_image_status(session, image.id, "ARCHIVED", note="归档")
    assert image.status == "ARCHIVED" and image.review_note == "归档" and image.reviewed_at is not None

    with pytest.raises(ValidationError):
        image_service.set_image_status(session, image.id, "BOGUS")
