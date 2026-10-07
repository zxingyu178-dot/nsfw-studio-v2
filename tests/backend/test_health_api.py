"""健康检查 API（Phase 0 规范 §十五）。"""
from __future__ import annotations


def test_health_returns_ok(client, settings):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "version": settings.app.version}


def test_root_info(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "NSFW Studio"
    assert body["api"] == "/api/v1/health"
