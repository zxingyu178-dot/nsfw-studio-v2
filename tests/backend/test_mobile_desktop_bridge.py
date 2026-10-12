"""Desktop 桥接 /api/v1/review/* 测试（与手机共用 ImageReviewSessionService）。"""
from __future__ import annotations


def test_desktop_review_create_and_queue(client, session_factory):
    # 直接在共享 DB 造图（走 session_factory）
    from app.services import image_service
    from app.storage.manager import StorageManager
    from PIL import Image as PILImage
    import io
    from app.core.config import load_settings  # noqa

    storage = StorageManager(client.app.state.settings)
    with session_factory() as session:
        buf = io.BytesIO()
        PILImage.new("RGB", (800, 600)).save(buf, format="PNG")
        img = image_service.import_engine_output(
            session, storage, data=buf.getvalue(), original_filename="d.png", source="comfyui",
        )

    r = client.post("/api/v1/review/sessions", json={"filter": {"status": "NEW"}})
    assert r.status_code == 201
    sid = r.json()["id"]
    assert r.json()["total_count"] >= 1

    q = client.get(f"/api/v1/review/sessions/{sid}/queue?page=1&page_size=50")
    assert q.status_code == 200
    assert q.json()["total"] >= 1

    # Desktop 响应**不包 mobile envelope**
    assert "success" not in q.json()


def test_desktop_decision_and_latest(client, session_factory):
    # 先造图并创建 session
    from app.services import image_service
    from app.storage.manager import StorageManager
    from PIL import Image as PILImage
    import io

    storage = StorageManager(client.app.state.settings)
    with session_factory() as session:
        buf = io.BytesIO()
        PILImage.new("RGB", (800, 600)).save(buf, format="PNG")
        image_service.import_engine_output(
            session, storage, data=buf.getvalue(), original_filename="d.png", source="comfyui",
        )

    created = client.post("/api/v1/review/sessions", json={})
    sid = created.json()["id"]

    r = client.get("/api/v1/review/sessions/latest")
    assert r.status_code == 200

    q = client.get(f"/api/v1/review/sessions/{sid}/queue").json()
    item = q["items"][0]
    d = client.post(f"/api/v1/review/sessions/{sid}/decision", json={
        "item_index": item["index"], "action": "KEEP",
        "expected_status": "NEW", "expected_updated_at": item["image"]["updated_at"],
    })
    assert d.status_code == 200
    assert d.json()["image"]["status"] == "KEEP"

    # 同一 session 被 latest 再次返回（不重建）
    latest = client.get("/api/v1/review/sessions/latest").json()
    assert latest["id"] == sid


def test_desktop_pairing_code_endpoint(client):
    r = client.post("/api/v1/mobile-review/pairing/code")
    assert r.status_code == 200
    code = r.json()["code"]
    assert len(code) == 6 and code.isdigit()
