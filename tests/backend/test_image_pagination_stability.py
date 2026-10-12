"""Phase 0.11.1 Task8：分页稳定 tie-breaker 测试。

- 多页拼接无重无漏（created_desc/created_asc）；
- created_at 相同时按 id 稳定排序；
- status/sort 过滤下 total 与页内一致。
"""
from __future__ import annotations

import io

from PIL import Image as PILImage

from app.models import Image


def _png(width=32, height=32, color=(10, 20, 30)) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _make_images(session, storage, n: int) -> list[str]:
    from app.services import image_service

    ids: list[str] = []
    for _ in range(n):
        img = image_service.import_engine_output(
            session, storage, data=_png(), original_filename="x.png", source="comfyui",
        )
        ids.append(img.id)
    return ids


def _collect_all(client, **params) -> list[str]:
    """按 page/page_size 遍历全部页，返回 id 顺序列表。"""
    seen: list[str] = []
    page = 1
    while True:
        resp = client.get("/api/v1/images", params={"page": page, "page_size": 20, **params})
        assert resp.status_code == 200
        body = resp.json()
        seen.extend(item["id"] for item in body["items"])
        if not body["has_next"]:
            return seen
        page += 1


def test_pagination_created_desc_no_dup_no_miss(client):
    from app.storage.manager import StorageManager

    storage = StorageManager(client.app.state.settings)
    with client.app.state.session_factory() as session:
        ids = _make_images(session, storage, 45)

    seen = _collect_all(client, sort="created_desc")
    assert len(seen) == 45
    assert len(set(seen)) == 45, "跨页拼接不得有重复 id"
    assert set(seen) == set(ids)


def test_pagination_created_asc_no_dup_no_miss(client):
    from app.storage.manager import StorageManager

    storage = StorageManager(client.app.state.settings)
    with client.app.state.session_factory() as session:
        ids = _make_images(session, storage, 43)

    seen = _collect_all(client, sort="created_asc")
    assert len(seen) == 43
    assert len(set(seen)) == 43
    assert set(seen) == set(ids)


def test_tie_breaker_stable_when_created_at_equal(client):
    from app.storage.manager import StorageManager

    storage = StorageManager(client.app.state.settings)
    with client.app.state.session_factory() as session:
        ids = _make_images(session, storage, 10)
        # 强制 created_at 相同 → 必须靠 id tie-breaker 稳定排序
        session.query(Image).update({Image.created_at: "2026-01-01T00:00:00+00:00"})
        session.commit()

    first = _collect_all(client, sort="created_desc")
    second = _collect_all(client, sort="created_desc")
    assert first == second, "created_at 相同时排序必须稳定（id 兜底）"
    # desc：id 倒序
    assert first == sorted(ids, reverse=True)


def test_status_filter_total_consistent(client):
    from app.services import image_service
    from app.storage.manager import StorageManager

    storage = StorageManager(client.app.state.settings)
    with client.app.state.session_factory() as session:
        ids = _make_images(session, storage, 10)
        # 把前 4 张置 KEEP
        for iid in ids[:4]:
            image_service.set_image_status(session, iid, "KEEP")

    resp = client.get("/api/v1/images", params={"status": "KEEP", "page": 1, "page_size": 5})
    body = resp.json()
    assert body["total"] == 4
    assert len(body["items"]) == 4
    assert {item["id"] for item in body["items"]} == set(ids[:4])
