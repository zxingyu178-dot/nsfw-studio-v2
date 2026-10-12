"""Decision 语义测试（KEEP/REJECT/favorite/RESET 映射 + 单事务）。"""
from __future__ import annotations


def _auth(mobile_client, session_factory):
    from app.services import mobile_pairing_service
    with session_factory() as session:
        code = mobile_pairing_service.generate_pairing_code(session)
    r = mobile_client.post("/mobile/pairing/verify", json={
        "installation_id": "dev-decision", "device_name": "p", "code": code,
    })
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _new_session(mobile_client, h):
    return mobile_client.post("/mobile/review/sessions", json={}, headers=h).json()["data"]["id"]


def test_decision_keep_reject_map(mobile_client, session_factory, make_mobile_image):
    make_mobile_image(2)
    h = _auth(mobile_client, session_factory)
    sid = _new_session(mobile_client, h)
    q = mobile_client.get(f"/mobile/review/sessions/{sid}/queue", headers=h).json()["data"]["items"]

    r0 = mobile_client.post(f"/mobile/review/sessions/{sid}/decision", json={
        "item_index": 0, "action": "KEEP",
        "expected_status": "NEW", "expected_updated_at": q[0]["image"]["updated_at"],
    }, headers=h).json()["data"]
    assert r0["image"]["status"] == "KEEP"

    r1 = mobile_client.post(f"/mobile/review/sessions/{sid}/decision", json={
        "item_index": 1, "action": "REJECT",
        "expected_status": "NEW", "expected_updated_at": q[1]["image"]["updated_at"],
    }, headers=h).json()["data"]
    assert r1["image"]["status"] == "REJECT"
    assert r1["session"]["seen_count"] == 2


def test_favorite_independent_of_status(mobile_client, session_factory, make_mobile_image):
    make_mobile_image(1)
    h = _auth(mobile_client, session_factory)
    sid = _new_session(mobile_client, h)
    q = mobile_client.get(f"/mobile/review/sessions/{sid}/queue", headers=h).json()["data"]["items"]

    # 只设 favorite，不改审核状态
    d = mobile_client.post(f"/mobile/review/sessions/{sid}/decision", json={
        "item_index": 0, "favorite": True,
        "expected_status": "NEW", "expected_updated_at": q[0]["image"]["updated_at"],
    }, headers=h).json()["data"]
    assert d["image"]["is_favorite"] is True
    assert d["image"]["status"] == "NEW"  # 审核状态独立，仍 NEW
    assert d["session"]["seen_count"] == 1  # 收藏也算已看


def test_reset_back_to_new(mobile_client, session_factory, make_mobile_image):
    make_mobile_image(1)
    h = _auth(mobile_client, session_factory)
    sid = _new_session(mobile_client, h)
    q = mobile_client.get(f"/mobile/review/sessions/{sid}/queue", headers=h).json()["data"]["items"]

    mobile_client.post(f"/mobile/review/sessions/{sid}/decision", json={
        "item_index": 0, "action": "KEEP",
        "expected_status": "NEW", "expected_updated_at": q[0]["image"]["updated_at"],
    }, headers=h)

    # RESET → NEW + seen=false
    d = mobile_client.post(f"/mobile/review/sessions/{sid}/decision", json={
        "item_index": 0, "action": "RESET",
        "expected_status": "KEEP", "expected_updated_at": None,
    }, headers=h).json()["data"]
    assert d["image"]["status"] == "NEW"

    q2 = mobile_client.get(f"/mobile/review/sessions/{sid}/queue", headers=h).json()["data"]["items"]
    assert q2[0]["seen"] is False


def test_no_permanent_delete_action(mobile_client, session_factory, make_mobile_image):
    make_mobile_image(1)
    h = _auth(mobile_client, session_factory)
    sid = _new_session(mobile_client, h)
    q = mobile_client.get(f"/mobile/review/sessions/{sid}/queue", headers=h).json()["data"]["items"]
    r = mobile_client.post(f"/mobile/review/sessions/{sid}/decision", json={
        "item_index": 0, "action": "DELETE",
        "expected_status": "NEW", "expected_updated_at": q[0]["image"]["updated_at"],
    }, headers=h)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "DECISION_ACTION_INVALID"
