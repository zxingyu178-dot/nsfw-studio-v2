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
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        # 开发/测试模式：dist 缺失，GET / 返回 JSON 应用信息
        body = response.json()
        assert body["name"] == "NSFW Studio"
        assert body["api"] == "/api/v1/health"
    else:
        # 日用模式：dist 存在，FastAPI 直接托管 React 构建产物 index.html
        assert "text/html" in content_type
