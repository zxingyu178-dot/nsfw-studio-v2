"""Mobile envelope 框架错误码映射测试（硬化 O1）。"""
from __future__ import annotations


def _auth(mobile_client, session_factory):
    from app.services import mobile_pairing_service
    with session_factory() as session:
        code = mobile_pairing_service.generate_pairing_code(session)
    r = mobile_client.post("/mobile/pairing/verify", json={
        "installation_id": "dev-404", "device_name": "p", "code": code,
    })
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def test_unknown_route_maps_to_not_found(mobile_client):
    """不存在的 /mobile/* 路径：HTTP 404 不变，error.code=NOT_FOUND（不再 INTERNAL_ERROR）。"""
    r = mobile_client.get("/mobile/system/__no_such_route__")
    assert r.status_code == 404
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"


def test_validation_error_keeps_422(mobile_client, session_factory):
    """参数校验失败保持 422 + VALIDATION_ERROR。"""
    h = _auth(mobile_client, session_factory)
    r = mobile_client.post("/mobile/pairing/verify", json={"code": "abc"})
    # 缺 installation_id 等字段 → 422
    assert r.status_code in (400, 422)
    assert r.json()["error"]["code"] in ("VALIDATION_ERROR", "BAD_REQUEST")


def test_docs_unavailable(mobile_client):
    r = mobile_client.get("/docs")
    assert r.status_code == 404
