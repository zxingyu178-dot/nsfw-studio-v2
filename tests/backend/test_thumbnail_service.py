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
    # Phase 0.11.1：新图入库即主动生成 thumbnail；这里先删掉自动生成的 variant+文件，
    # 制造"历史缺图"条件，再由回填补齐。
    for img in (img_a, img_b):
        variant = thumbnail_service.find_thumbnail_variant(session, img.id)
        assert variant is not None  # 入库已主动生成
        storage.absolutize(variant.path).unlink()
        session.delete(variant)
    session.commit()
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
    # 入库已主动生成 thumbnail；删掉它（variant+文件），制造"需按需生成"条件，
    # 再把原图替换为垃圾内容，按需生成应抛出 ValidationError。
    variant = thumbnail_service.find_thumbnail_variant(session, image.id)
    storage.absolutize(variant.path).unlink()
    session.delete(variant)
    session.commit()
    storage.absolutize(image.file_path).write_bytes(b"not an image")

    try:
        thumbnail_service.get_or_create_thumbnail(session, storage, image)
        raise AssertionError("损坏原图应抛出 ValidationError")
    except ValidationError as error:
        assert error.code == "THUMBNAIL_FAILED"


def test_new_image_import_auto_generates_thumbnail(session, settings):
    """Phase 0.11.1 P1-3：新图入库后 thumbnail variant 已存在（用内存字节，未重读盘）。"""
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import(session, storage, 1024, 768)

    variant = thumbnail_service.find_thumbnail_variant(session, image.id)
    assert variant is not None, "入库后应已主动生成 thumbnail"
    from app.storage.manager import StorageManager as _SM
    assert _SM(settings).absolutize(variant.path).is_file()
    with PILImage.open(_SM(settings).absolutize(variant.path)) as im:
        assert im.format == "WEBP"


def test_active_thumbnail_failure_does_not_break_import(session, settings, monkeypatch):
    """缩略图渲染抛错时：落库仍成功、无异常泄漏（仅 warning）。"""
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)

    def boom(_data, **_kw):
        raise RuntimeError("render exploded")

    monkeypatch.setattr(thumbnail_service, "render_webp", boom)

    # 不应抛出
    image = image_service.import_engine_output(
        session, storage, data=_png_bytes(640, 480), original_filename="x.png",
        source="comfyui",
    )
    assert image.id
    # 图片行已落库（原图文件在）
    assert storage.absolutize(image.file_path).is_file()
    # thumbnail 未生成（但不影响落库）
    assert thumbnail_service.find_thumbnail_variant(session, image.id) is None


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
