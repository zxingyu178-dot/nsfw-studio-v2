"""Phase 0.11.1 P1-2：ImagePicker 历史可达 API 契约测试（API 层）。

- 构造 >120 张图，page/page_size 可遍历到最早一张（has_next 最终 false、无重漏）；
- 各筛选映射正确：最近(created_desc)/待审核(NEW)/保留(KEEP)/收藏(favorite=true)；
- thumbnail/preview 端点返回 200。
"""
from __future__ import annotations

import io

from PIL import Image as PILImage

from app.models import Image


def _png(width=32, height=32) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (width, height), (80, 90, 100)).save(buffer, format="PNG")
    return buffer.getvalue()


def _make_images(client, n: int) -> list[str]:
    from app.services import image_service
    from app.storage.manager import StorageManager

    storage = StorageManager(client.app.state.settings)
    ids: list[str] = []
    with client.app.state.session_factory() as session:
        for _ in range(n):
            img = image_service.import_engine_output(
                session, storage, data=_png(), original_filename="x.png", source="comfyui",
            )
            ids.append(img.id)
    return ids


def _collect(client, **params) -> list[str]:
    seen: list[str] = []
    page = 1
    while True:
        resp = client.get("/api/v1/images", params={"page": page, "page_size": 25, **params})
        body = resp.json()
        seen.extend(i["id"] for i in body["items"])
        if not body["has_next"]:
            return seen
        page += 1


def test_picker_traverses_to_earliest(client):
    ids = _make_images(client, 130)  # >120
    seen = _collect(client, sort="created_desc")
    assert len(seen) == 130
    assert len(set(seen)) == 130, "遍历到最早一张，不得有重漏"
    assert set(seen) == set(ids)


def test_picker_filter_mappings(client):
    from app.services import image_service

    ids = _make_images(client, 20)
    with client.app.state.session_factory() as session:
        # 3 张待审核(NEW，默认)；5 张保留(KEEP)；4 张 KEEP+收藏(favorite=true)
        for iid in ids[3:8]:
            image_service.set_image_status(session, iid, "KEEP")
        for iid in ids[8:12]:
            image_service.set_image_status(session, iid, "KEEP")
            image_service.set_favorite(session, iid, True)

    new_ids = set(_collect(client, status="NEW"))
    keep_ids = set(_collect(client, status="KEEP"))
    fav_ids = set(_collect(client, favorite="true"))

    # NEW = 前 3 张 + 未触碰的后 8 张（ids[12:20]）
    assert new_ids == set(ids[:3]) | set(ids[12:20])
    assert keep_ids == set(ids[3:12])
    # 收藏筛选：favorite=true 的 4 张
    assert fav_ids == set(ids[8:12])


def test_picker_thumbnail_and_preview_200(client):
    ids = _make_images(client, 3)
    for iid in ids:
        t = client.get(f"/api/v1/images/{iid}/thumbnail")
        assert t.status_code == 200
        assert t.headers["content-type"] == "image/webp"
        p = client.get(f"/api/v1/images/{iid}/preview")
        assert p.status_code == 200
        assert p.headers["content-type"] == "image/webp"
