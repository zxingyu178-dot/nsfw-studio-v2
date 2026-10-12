"""并发冲突：decision 乐观锁 → 409 REVIEW_CONFLICT + 当前权威 Image。"""
from __future__ import annotations


def _auth(mobile_client, session_factory):
    from app.services import mobile_pairing_service
    with session_factory() as session:
        code = mobile_pairing_service.generate_pairing_code(session)
    r = mobile_client.post("/mobile/pairing/verify", json={
        "installation_id": "dev-conflict", "device_name": "p", "code": code,
    })
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def test_conflict_on_stale_status(mobile_client, session_factory, make_mobile_image):
    make_mobile_image(1)
    h = _auth(mobile_client, session_factory)
    sid = mobile_client.post("/mobile/review/sessions", json={}, headers=h).json()["data"]["id"]
    q = mobile_client.get(f"/mobile/review/sessions/{sid}/queue", headers=h).json()["data"]["items"]
    item = q[0]

    # 第一次 KEEP 成功
    ok = mobile_client.post(f"/mobile/review/sessions/{sid}/decision", json={
        "item_index": 0, "action": "KEEP",
        "expected_status": "NEW", "expected_updated_at": item["image"]["updated_at"],
    }, headers=h)
    assert ok.status_code == 200

    # 第二次仍以旧 expected_status=NEW 提交 → 409 REVIEW_CONFLICT
    conflict = mobile_client.post(f"/mobile/review/sessions/{sid}/decision", json={
        "item_index": 0, "action": "REJECT",
        "expected_status": "NEW", "expected_updated_at": item["image"]["updated_at"],
    }, headers=h)
    assert conflict.status_code == 409
    body = conflict.json()
    assert body["success"] is False
    assert body["error"]["code"] == "REVIEW_CONFLICT"
    # 返回当前权威 Image（已是 KEEP）
    assert body["error"]["details"]["current_status"] == "KEEP"
    assert body["error"]["details"]["image"]["status"] == "KEEP"


def test_conflict_on_stale_updated_at(mobile_client, session_factory, make_mobile_image):
    make_mobile_image(1)
    h = _auth(mobile_client, session_factory)
    sid = mobile_client.post("/mobile/review/sessions", json={}, headers=h).json()["data"]["id"]
    q = mobile_client.get(f"/mobile/review/sessions/{sid}/queue", headers=h).json()["data"]["items"]
    item = q[0]

    mobile_client.post(f"/mobile/review/sessions/{sid}/decision", json={
        "item_index": 0, "favorite": True,
        "expected_status": "NEW", "expected_updated_at": item["image"]["updated_at"],
    }, headers=h)

    # 用旧 updated_at 再提交 → 409
    conflict = mobile_client.post(f"/mobile/review/sessions/{sid}/decision", json={
        "item_index": 0, "action": "KEEP",
        "expected_status": "NEW", "expected_updated_at": item["image"]["updated_at"],
    }, headers=h)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "REVIEW_CONFLICT"
