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


def test_desktop_devices_list_no_secret_and_revoke(client, session_factory):
    # 先在共享 DB 造一台已配对设备（含 token_hash）
    from app.services import mobile_pairing_service
    with session_factory() as session:
        code = mobile_pairing_service.generate_pairing_code(session)
    # 用 desktop 直接走 verify 逻辑造设备
    from fastapi.testclient import TestClient  # noqa
    # 直接调服务层 verify（模拟手机配对）
    with session_factory() as session:
        paired = mobile_pairing_service.verify_pairing(
            session, installation_id="dev-list-1", device_name="Phone", code=code,
        )

    # Desktop loopback 列表：不含 token_hash / token
    r = client.get("/api/v1/mobile-review/devices")
    assert r.status_code == 200
    devices = r.json()["devices"]
    assert any(d["installation_id"] == "dev-list-1" for d in devices)
    blob = str(devices)
    assert "token_hash" not in blob
    assert paired.token not in blob

    # 吊销 → token 立即 401 DEVICE_REVOKED
    rid = [d for d in devices if d["installation_id"] == "dev-list-1"][0]["id"]
    rev = client.post(f"/api/v1/mobile-review/devices/{rid}/revoke")
    assert rev.status_code == 200
    assert rev.json()["revoked"] is True

    # 该 token 再鉴权 → DEVICE_REVOKED
    from app.services import mobile_pairing_service as mps
    with session_factory() as session:
        try:
            mps.authenticate_token(session, paired.token)
            assert False, "应抛 DEVICE_REVOKED"
        except mps.DeviceRevoked:
            pass


def test_desktop_error_passes_details(client, session_factory):
    """409 REVIEW_CONFLICT 的 details（权威 image）应透传到 Desktop 错误体。"""
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

    sid = client.post("/api/v1/review/sessions", json={}).json()["id"]
    item = client.get(f"/api/v1/review/sessions/{sid}/queue").json()["items"][0]
    # 第一次 KEEP
    client.post(f"/api/v1/review/sessions/{sid}/decision", json={
        "item_index": item["index"], "action": "KEEP",
        "expected_status": "NEW", "expected_updated_at": item["image"]["updated_at"],
    })
    # 第二次用旧 expected_status → 409
    conflict = client.post(f"/api/v1/review/sessions/{sid}/decision", json={
        "item_index": item["index"], "action": "REJECT",
        "expected_status": "NEW", "expected_updated_at": item["image"]["updated_at"],
    })
    assert conflict.status_code == 409
    body = conflict.json()
    assert body["error"]["code"] == "REVIEW_CONFLICT"
    assert body["error"]["details"]["current_status"] == "KEEP"
    assert body["error"]["details"]["image"]["status"] == "KEEP"
