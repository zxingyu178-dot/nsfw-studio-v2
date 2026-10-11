"""Phase 0.11 ThumbnailService 测试（512px WebP q80 按需生成 + 回填）。"""
from __future__ import annotations

import io

from PIL import Image as PILImage

from app.services import image_service, thumbnail_service


def _png_bytes(width: int, height: int, color=(120, 80, 200)) -> bytes:
    """生成完全可解码的 PNG（缩略图编码器需要真实像素）。"""
    buffer = io.BytesIO()
    PILImage.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _import(session, storage, width=1024, height=768):
    return image_service.import_engine_output(
        session, storage, data=_png_bytes(width, height), original_filename="a.png",
        source="comfyui",
    )


def test_generate_thumbnail_records_variant(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import(session, storage, 1024, 768)

    path, variant = thumbnail_service.get_or_create_thumbnail(session, storage, image)

    assert path.is_file()
    assert variant.variant_type == "thumbnail"
    assert variant.format == "webp"
    # 1024x768 → 最长边下采样到 512 → 512x384（等比）
    assert (variant.width, variant.height) == (512, 384)
    assert variant.path.startswith("images/thumbnails/")
    # 解码确认是 WebP
    with PILImage.open(path) as im:
        assert im.format == "WEBP"


def test_thumbnail_reused_when_present(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import(session, storage)

    _p1, v1 = thumbnail_service.get_or_create_thumbnail(session, storage, image)
    _p2, v2 = thumbnail_service.get_or_create_thumbnail(session, storage, image)

    assert v1.id == v2.id, "同图第二次必须复用同一 thumbnail variant，不得重复创建"
    assert thumbnail_service.find_thumbnail_variant(session, image.id) is not None


def test_thumbnail_regenerated_when_file_deleted(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import(session, storage)
    _p, variant = thumbnail_service.get_or_create_thumbnail(session, storage, image)

    storage.absolutize(variant.path).unlink()  # 模拟缩略图文件被删

    path2, variant2 = thumbnail_service.get_or_create_thumbnail(session, storage, image)
    assert variant2.id == variant.id, "文件丢失应复用同一 variant 行并更新路径"
    assert path2.is_file()


def test_backfill_missing_thumbnails(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    img_a = _import(session, storage, 800, 600)
    img_b = _import(session, storage, 640, 480)
    # 两张都尚未生成缩略图
    assert thumbnail_service.find_thumbnail_variant(session, img_a.id) is None
    assert thumbnail_service.find_thumbnail_variant(session, img_b.id) is None

    created = thumbnail_service.backfill_missing_thumbnails(session, storage)
    assert created == 2
    assert thumbnail_service.find_thumbnail_variant(session, img_a.id) is not None
    assert thumbnail_service.find_thumbnail_variant(session, img_b.id) is not None

    # 再次回填：全部已有缩略图 → 0
    assert thumbnail_service.backfill_missing_thumbnails(session, storage) == 0


def test_corrupt_original_raises_clean_error(session, settings):
    from app.core.errors import ValidationError
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import(session, storage)
    # 把原图文件替换为垃圾内容（DB 行仍在）
    storage.absolutize(image.file_path).write_bytes(b"not an image")

    try:
        thumbnail_service.get_or_create_thumbnail(session, storage, image)
        raise AssertionError("损坏原图应抛出 ValidationError")
    except ValidationError as error:
        assert error.code == "THUMBNAIL_FAILED"


def test_api_thumbnail_endpoint(client):
    """GET /images/{id}/thumbnail 返回 WebP 并落 variant。"""
    from app.storage.manager import StorageManager

    storage = StorageManager(client.app.state.settings)
    image_id: str | None = None
    with client.app.state.session_factory() as session:
        image = _import(session, storage, 1024, 768)
        image_id = image.id

    resp = client.get(f"/api/v1/images/{image_id}/thumbnail")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/webp"
    with PILImage.open(io.BytesIO(resp.content)) as im:
        assert im.format == "WEBP"

    # 第二次命中已落库的 variant（仍 200）
    assert client.get(f"/api/v1/images/{image_id}/thumbnail").status_code == 200
