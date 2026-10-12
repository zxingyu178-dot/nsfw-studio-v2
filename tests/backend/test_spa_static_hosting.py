"""生产静态托管 + SPA catch-all 测试（Commit 2）。

全部用 tmp_path 构造独立 dist，绝依赖真实 ``frontend/dist``：
- 客户端路由（/、/generate、/gallery、/deep/route）返回 index.html；
- 静态资源 /assets/* 由 StaticFiles 直接返回；
- 真实 /api/v1/health 仍为 JSON；未匹配的 /api/* 返回 404 且非 HTML；
- dist 缺失时 create_app 的 GET / 仍返回原 JSON 应用信息。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.core.static_hosting import register_static_hosting


def _build_app(dist_dir: Path | None) -> FastAPI:
    """构造一个含 /api/v1 路由 + 静态托管的最小应用。"""
    app = FastAPI()
    api = APIRouter(prefix="/api/v1")

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api)
    register_static_hosting(app, dist_dir=dist_dir)
    return app


def _make_dist(root: Path) -> Path:
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>SPA_ROOT</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('spa');", encoding="utf-8")
    return dist


def test_spa_client_routes_return_index_html(tmp_path: Path) -> None:
    client = TestClient(_build_app(_make_dist(tmp_path)))
    for path in ("/", "/generate", "/gallery", "/prompts", "/settings", "/deep/route"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert resp.text == "<html>SPA_ROOT</html>", path


def test_static_asset_served(tmp_path: Path) -> None:
    client = TestClient(_build_app(_make_dist(tmp_path)))
    resp = client.get("/assets/app.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text


def test_api_health_still_json(tmp_path: Path) -> None:
    client = TestClient(_build_app(_make_dist(tmp_path)))
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_unknown_api_returns_404_not_html(tmp_path: Path) -> None:
    client = TestClient(_build_app(_make_dist(tmp_path)))
    resp = client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    assert "text/html" not in resp.headers.get("content-type", "")
    assert "<html>" not in resp.text
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_missing_dist_keeps_json_root(tmp_path: Path, monkeypatch) -> None:
    """dist 缺失时 create_app 不启用 SPA，GET / 返回原 JSON 应用信息。"""
    from app.core import static_hosting
    from app.main import create_app

    monkeypatch.setattr(static_hosting, "DEFAULT_DIST_DIR", tmp_path / "no_such_dist")
    app = create_app()  # 不进入 lifespan，仅验证路由注册
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "NSFW Studio"
    assert body["api"] == "/api/v1/health"
