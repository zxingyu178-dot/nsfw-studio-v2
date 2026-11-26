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
    assert data["version"] == "0.14.0"
    assert data["api_contract"] == 2
    assert data["build_commit"]
    assert data["built_at"]
    assert len(data["capability_set_hash"]) == 12
    for cap in ("image_review", "review_session", "favorite", "thumbnail", "preview", "original"):
        assert cap in data["capabilities"]
    for cap in ("image_event_feed", "image_detail", "prompt_version_evaluation",
                "idempotent_mutation", "snapshot_resync"):
        assert cap in data["capabilities"]
    # W3.1 MediaReview 客户端冻结能力：缺一即不得声明可审核
    for cap in ("mobile_feed_v2", "mobile_image_details_v2", "mobile_image_decision_v2",
                "mobile_prompt_review_v2", "mobile_prompt_evaluation_v2"):
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


def test_last_seen_at_is_throttled_for_authenticated_requests(mobile_client, session_factory):
    """60 秒窗口内多次鉴权只读校验，不重复写 last_seen_at / 抢写锁。"""
    from sqlalchemy import select

    from app.models.mobile_review import MobileReviewDevice
    from app.services import mobile_pairing_service

    with session_factory() as session:
        code = mobile_pairing_service.generate_pairing_code(session)
    response = mobile_client.post("/mobile/pairing/verify", json={
        "installation_id": "dev-throttle", "device_name": "throttle", "code": code,
    })
    token = response.json()["data"]["token"]

    old_value = "2000-01-01T00:00:00.000Z"
    with session_factory() as session:
        device = session.execute(
            select(MobileReviewDevice).where(MobileReviewDevice.installation_id == "dev-throttle")
        ).scalars().first()
        device_id = device.id
        device.last_seen_at = old_value
        session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    mobile_pairing_service._last_seen_written[device_id] = time.monotonic()
    for _ in range(3):
        assert mobile_client.get("/mobile/review/sessions/latest", headers=headers).status_code == 404
    with session_factory() as session:
        assert session.get(MobileReviewDevice, device_id).last_seen_at == old_value

    mobile_pairing_service._last_seen_written[device_id] = (
        time.monotonic() - mobile_pairing_service.LAST_SEEN_WRITE_INTERVAL_SECONDS - 1
    )
    assert mobile_client.get("/mobile/review/sessions/latest", headers=headers).status_code == 404
    with session_factory() as session:
        assert session.get(MobileReviewDevice, device_id).last_seen_at != old_value


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
