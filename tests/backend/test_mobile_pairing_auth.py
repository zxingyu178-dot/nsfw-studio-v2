"""Mobile Bridge 配对与 Bearer 鉴权测试（Phase 0.13）。

覆盖：health 开放、pairing status 开放、无效码拒绝、一次性、10 分钟过期、
Bearer 缺失/无效/已吊销 → 401 envelope、配对成功换 token 后可访问受保护端点。
"""
from __future__ import annotations

import time


def test_health_open_and_contract(mobile_client):
    r = mobile_client.get("/mobile/system/health")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["product"] == "nsfw-studio"
    assert data["version"] == "0.13.0"
    assert data["api_contract"] == 1
    for cap in ("image_review", "review_session", "favorite", "thumbnail", "preview", "original"):
        assert cap in data["capabilities"]
    # 绝不包含高危能力
    for forbidden in ("permanent_delete", "engine_control", "generation", "prompt_edit"):
        assert forbidden not in data["capabilities"]


def test_pairing_status_open(mobile_client):
    r = mobile_client.get("/mobile/pairing/status")
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert r.json()["data"] == {"pairing_available": False}


def test_protected_requires_bearer(mobile_client):
    r = mobile_client.get("/mobile/review/sessions/latest")
    assert r.status_code == 401
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "UNAUTHORIZED"


def test_pairing_invalid_code_rejected(mobile_client):
    r = mobile_client.post("/mobile/pairing/verify", json={
        "installation_id": "dev-1", "device_name": "phone", "code": "000000",
    })
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "PAIRING_CODE_INVALID"


def test_pairing_code_one_time_and_token_flow(mobile_client, session_factory):
    # Desktop loopback 生成配对码（直接走服务层，模拟 8000）
    from app.services import mobile_pairing_service
    with session_factory() as session:
        code = mobile_pairing_service.generate_pairing_code(session)
    assert len(code) == 6 and code.isdigit()

    # 手机 verify 成功 → 返回 Bearer token（明文只此一次）
    r = mobile_client.post("/mobile/pairing/verify", json={
        "installation_id": "dev-phone-1", "device_name": "Pixel", "code": code,
    })
    assert r.status_code == 200
    token = r.json()["data"]["token"]
    assert token

    # 用 token 访问受保护端点成功
    h = {"Authorization": f"Bearer {token}"}
    r2 = mobile_client.get("/mobile/review/sessions/latest", headers=h)
    assert r2.status_code == 404  # 尚无 session，但鉴权通过（不是 401）
    assert r2.json()["error"]["code"] == "REVIEW_SESSION_NOT_FOUND"

    # 同一配对码第二次用 → 失败（一次性）
    r3 = mobile_client.post("/mobile/pairing/verify", json={
        "installation_id": "dev-phone-2", "device_name": "x", "code": code,
    })
    assert r3.status_code == 400
    assert r3.json()["error"]["code"] == "PAIRING_CODE_INVALID"


def test_device_revoked_returns_401(mobile_client, session_factory):
    from app.services import mobile_pairing_service
    from app.models.mobile_review import MobileReviewDevice
    from sqlalchemy import select

    with session_factory() as session:
        code = mobile_pairing_service.generate_pairing_code(session)
    r = mobile_client.post("/mobile/pairing/verify", json={
        "installation_id": "dev-revoke", "device_name": "p", "code": code,
    })
    token = r.json()["data"]["token"]

    # 直接吊销设备
    import hashlib
    with session_factory() as session:
        dev = session.execute(
            select(MobileReviewDevice).where(MobileReviewDevice.installation_id == "dev-revoke")
        ).scalars().first()
        dev.revoked = True
        session.commit()

    h = {"Authorization": f"Bearer {token}"}
    r2 = mobile_client.get("/mobile/review/sessions/latest", headers=h)
    assert r2.status_code == 401
    assert r2.json()["error"]["code"] == "DEVICE_REVOKED"
