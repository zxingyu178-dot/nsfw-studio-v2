"""Phase 0.12：GET /api/v1/images/stats 全局聚合统计测试。

覆盖：
- status / favorite 各桶计数正确，favorites 为独立交叉计数；
- 与 GET /images 完全相同的过滤口径（过滤后 total 必须与 list total 一致）；
- job_id / source / kind / search / status / favorite 过滤正确性；
- 非法 status 复用 list 的校验（400）。
"""
from __future__ import annotations

import io

from PIL import Image as PILImage


def _png(seed: int = 0) -> bytes:
    """不同 seed 产生不同像素内容（import 按 sha256 去重，内容必须各不相同）。"""
    buffer = io.BytesIO()
    PILImage.new("RGB", (32, 32), ((seed * 37 + 5) % 256, (seed * 91 + 13) % 256, (seed * 53 + 29) % 256)).save(
        buffer, format="PNG"
    )
    return buffer.getvalue()


def _import_one(client, filename: str, seed: int) -> str:
    """经服务层导入一张图（source=import，job_id=None），返回 image_id。"""
    from app.services import image_service
    from app.storage.manager import StorageManager

    storage = StorageManager(client.app.state.settings)
    with client.app.state.session_factory() as session:
        result = image_service.import_images_batch(
            session, storage, [(filename, "image/png", _png(seed))]
        )
        return result.imported[0].id


def _set_status(client, image_id: str, status: str) -> None:
    from app.services import image_service

    with client.app.state.session_factory() as session:
        image_service.set_image_status(session, image_id, status)


def _set_favorite(client, image_id: str, favorite: bool) -> None:
    from app.services import image_service

    with client.app.state.session_factory() as session:
        image_service.set_favorite(session, image_id, favorite)


def _seed_gallery(client) -> dict[str, str]:
    a = _import_one(client, "apple.png", 1)   # NEW + favorite
    b = _import_one(client, "banana.png", 2)  # KEEP + favorite
    c = _import_one(client, "cherry.png", 3)  # REJECT
    d = _import_one(client, "date.png", 4)    # ARCHIVED
    _set_favorite(client, a, True)
    _set_status(client, b, "KEEP")
    _set_favorite(client, b, True)
    _set_status(client, c, "REJECT")
    _set_status(client, d, "ARCHIVED")
    return {"a": a, "b": b, "c": c, "d": d}


def test_stats_status_buckets_and_favorites(client):
    _seed_gallery(client)
    resp = client.get("/api/v1/images/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "total": 4,
        "new": 1,      # a
        "keep": 1,     # b
        "reject": 1,   # c
        "archived": 1, # d
        "favorites": 2,  # a(NEW+fav) + b(KEEP+fav)：独立交叉计数
    }


def test_stats_total_matches_list_total_under_filters(client):
    _seed_gallery(client)
    # 无过滤
    stats = client.get("/api/v1/images/stats").json()
    listing = client.get("/api/v1/images", params={"page_size": 100}).json()
    assert stats["total"] == listing["total"] == 4
    # status=KEEP 过滤
    stats = client.get("/api/v1/images/stats", params={"status": "KEEP"}).json()
    listing = client.get("/api/v1/images", params={"status": "KEEP", "page_size": 100}).json()
    assert stats["total"] == listing["total"] == 1
    assert stats["keep"] == 1
    assert stats["new"] == stats["reject"] == stats["archived"] == 0
    # favorite=true 过滤：a(NEW+fav) + b(KEEP+fav)
    stats = client.get("/api/v1/images/stats", params={"favorite": "true"}).json()
    listing = client.get("/api/v1/images", params={"favorite": "true", "page_size": 100}).json()
    assert stats["total"] == listing["total"] == 2
    assert stats["favorites"] == 2
    assert stats["new"] == 1 and stats["keep"] == 1


def test_stats_search_filter(client):
    _seed_gallery(client)
    resp = client.get("/api/v1/images/stats", params={"search": "apple"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["new"] == 1
    assert body["favorites"] == 1  # apple 是 NEW+favorite


def test_stats_source_filter(client):
    _seed_gallery(client)
    imported = client.get("/api/v1/images/stats", params={"source": "import"}).json()
    assert imported["total"] == 4
    generated = client.get("/api/v1/images/stats", params={"source": "comfyui"}).json()
    assert generated["total"] == 0


def test_stats_invalid_status_rejected(client):
    resp = client.get("/api/v1/images/stats", params={"status": "NOT_A_STATUS"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "IMAGE_STATUS_INVALID"
