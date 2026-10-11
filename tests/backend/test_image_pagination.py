"""Phase 0.11 图库标准分页（GET /api/v1/images）测试。

覆盖：
- 标准分页 page/page_size/has_next，末页可达、历史图片可完整访问（翻完所有页 = 全量）；
- sort 枚举（created_desc/created_asc/favorite/size）与非法排序拒绝；
- 新审核 status 过滤；
- 旧 limit/offset 调用方兼容（不被破坏）；
- 单图 DTO 携带新审核字段 status/reviewed_at/review_note。
"""
from __future__ import annotations

import pytest

from app.services import image_service


def _seed_images(client, png_bytes, count: int) -> list[str]:
    """直接在共享 DataRoot 导入 count 张图片，返回其 id 列表（导入顺序）。"""
    from app.storage.manager import StorageManager

    storage = StorageManager(client.app.state.settings)
    ids: list[str] = []
    with client.app.state.session_factory() as session:
        for _ in range(count):
            image = image_service.import_engine_output(
                session, storage, data=png_bytes, original_filename="a.png", source="comfyui",
            )
            ids.append(image.id)
    return ids


def test_pagination_pages_all_images_accessible(client, png_bytes):
    """1000 级规模模拟：85 张 → 3 页（40/40/5），末页 has_next=false，三页并集=85。"""
    expected = _seed_images(client, png_bytes, 85)

    page1 = client.get("/api/v1/images", params={"page": 1, "page_size": 40}).json()
    assert page1["total"] == 85
    assert page1["page"] == 1 and page1["page_size"] == 40
    assert len(page1["items"]) == 40
    assert page1["has_next"] is True

    page2 = client.get("/api/v1/images", params={"page": 2, "page_size": 40}).json()
    assert len(page2["items"]) == 40
    assert page2["page"] == 2
    assert page2["has_next"] is True

    page3 = client.get("/api/v1/images", params={"page": 3, "page_size": 40}).json()
    assert len(page3["items"]) == 5
    assert page3["page"] == 3
    assert page3["has_next"] is False

    seen = {item["id"] for item in page1["items"] + page2["items"] + page3["items"]}
    assert seen == set(expected), "三页并集必须覆盖全部历史图片，不得遗漏"

    # 超出末页：空 items，但 total/has_next 语义正确
    page9 = client.get("/api/v1/images", params={"page": 9, "page_size": 40}).json()
    assert page9["items"] == []
    assert page9["has_next"] is False


def test_default_page_size_is_40(client, png_bytes):
    """默认 page=1、page_size=40。"""
    _seed_images(client, png_bytes, 5)
    resp = client.get("/api/v1/images").json()
    assert resp["page"] == 1
    assert resp["page_size"] == 40
    assert len(resp["items"]) == 5


def test_sort_enums(client, png_bytes):
    _seed_images(client, png_bytes, 6)
    for sort in ("created_desc", "created_asc", "favorite", "size"):
        resp = client.get("/api/v1/images", params={"sort": sort})
        assert resp.status_code == 200, f"sort={sort} 应合法"
    bad = client.get("/api/v1/images", params={"sort": "not_a_sort"})
    assert bad.status_code == 400, "非法 sort 应被校验拒绝（ValidationError → 400）"


def test_status_filter(client, png_bytes):
    """新审核 status 过滤：把第 1 张置为 KEEP，其余保持 NEW（直接 ORM 置位）。"""
    from app.core.timeutil import utc_now_iso
    from app.models import Image

    expected = _seed_images(client, png_bytes, 10)
    target = expected[0]
    with client.app.state.session_factory() as session:
        image = session.get(Image, target)
        image.status = "KEEP"
        image.reviewed_at = utc_now_iso()
        session.commit()

    keep = client.get("/api/v1/images", params={"status": "KEEP"}).json()
    assert keep["total"] == 1
    assert keep["items"][0]["id"] == target

    new = client.get("/api/v1/images", params={"status": "NEW"}).json()
    assert new["total"] == 9


def test_image_dto_carries_review_fields(client, png_bytes):
    expected = _seed_images(client, png_bytes, 1)
    resp = client.get("/api/v1/images", params={"status": "NEW"}).json()
    item = resp["items"][0]
    assert item["id"] == expected[0]
    assert item["status"] == "NEW"
    assert "reviewed_at" in item
    assert item["review_note"] == ""


def test_legacy_limit_offset_still_works(client, png_bytes):
    """旧调用方传 limit/offset 必须不被破坏（一次性拉取、items 正常）。"""
    expected = _seed_images(client, png_bytes, 3)
    resp = client.get("/api/v1/images", params={"limit": 200}).json()
    assert resp["total"] == 3
    assert {i["id"] for i in resp["items"]} == set(expected)
