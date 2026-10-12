"""Phase 0.11.1 P1-3：历史缩略图/预览回填 API 测试。

- 启动/状态/停止；进度计数正确；单张失败跳过；
- 重复调用不重复起；kind=preview 同样工作。
"""
from __future__ import annotations

import io
import time

from PIL import Image as PILImage

from app.models import Image, ImageVariant


def _png(width=640, height=480, color=(120, 80, 200)) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (width, height), color).save(buffer, format="PNG")
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


def _strip_thumbnails(client, ids: list[str]) -> None:
    """删掉自动生成的 thumbnail variant+文件，制造"历史缺图"条件。"""
    from app.storage.manager import StorageManager

    storage = StorageManager(client.app.state.settings)
    with client.app.state.session_factory() as session:
        rows = session.query(ImageVariant).filter(
            ImageVariant.image_id.in_(ids), ImageVariant.variant_type == "thumbnail"
        ).all()
        for row in rows:
            storage.absolutize(row.path).unlink(missing_ok=True)
            session.delete(row)
        session.commit()


def _wait_done(client, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get("/api/v1/images/thumbnails/backfill/status")
        data = resp.json()
        if not data["running"]:
            return data
        time.sleep(0.05)
    return client.get("/api/v1/images/thumbnails/backfill/status").json()


def test_backfill_start_status_stop(client):
    ids = _make_images(client, 4)
    _strip_thumbnails(client, ids)

    resp = client.post("/api/v1/images/thumbnails/backfill", json={"kind": "thumbnail"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "thumbnail"
    assert body["total"] == 4

    final = _wait_done(client)
    assert final["running"] is False
    assert final["done"] == 4
    assert final["failed"] == 0

    # 全部补齐后再查状态
    status = client.get("/api/v1/images/thumbnails/backfill/status").json()
    assert status["done"] == 4

    stop = client.post("/api/v1/images/thumbnails/backfill/stop").json()
    assert stop["running"] is False


def test_backfill_repeated_call_does_not_double_start(client):
    ids = _make_images(client, 3)
    _strip_thumbnails(client, ids)

    r1 = client.post("/api/v1/images/thumbnails/backfill", json={"kind": "thumbnail"}).json()
    # 立即再调一次：应返回同一任务（running），不重复起
    r2 = client.post("/api/v1/images/thumbnails/backfill", json={"kind": "thumbnail"}).json()
    assert r2["running"] in (True, False)
    assert r2["kind"] == "thumbnail"
    # total 不会翻倍（同一批候选）
    assert r2["total"] == r1["total"]

    final = _wait_done(client)
    assert final["done"] == 3


def test_backfill_skips_failed_image(client, monkeypatch):
    """单张失败跳过不阻断；failed 计数正确。"""
    from app.services import thumbnail_service

    ids = _make_images(client, 3)
    _strip_thumbnails(client, ids)

    real_get = thumbnail_service.get_or_create_variant
    call_count = {"n": 0}

    def flaky(session, storage, image, variant_type):
        call_count["n"] += 1
        # 让第一张失败
        if call_count["n"] == 1:
            raise RuntimeError("boom on first")
        return real_get(session, storage, image, variant_type)

    monkeypatch.setattr(thumbnail_service, "get_or_create_variant", flaky)

    resp = client.post("/api/v1/images/thumbnails/backfill", json={"kind": "thumbnail"})
    assert resp.status_code == 200
    final = _wait_done(client)
    assert final["done"] == 2
    assert final["failed"] == 1


def test_backfill_kind_preview(client):
    ids = _make_images(client, 3)
    # preview 从未生成过 → 候选 3
    resp = client.post("/api/v1/images/thumbnails/backfill", json={"kind": "preview"})
    assert resp.status_code == 200
    assert resp.json()["kind"] == "preview"
    final = _wait_done(client)
    assert final["done"] == 3
    assert final["failed"] == 0

    # preview variant 落库
    with client.app.state.session_factory() as session:
        for iid in ids:
            row = session.query(ImageVariant).filter(
                ImageVariant.image_id == iid, ImageVariant.variant_type == "preview"
            ).first()
            assert row is not None
            assert "images/previews/" in row.path
