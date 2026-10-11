"""Phase 0.11 废片清理（cleanup-rejected）两阶段测试。"""
from __future__ import annotations

import io

import pytest
from PIL import Image as PILImage

from app.core.errors import NotFoundError
from app.services import cleanup_service, image_service, thumbnail_service


def _real_png(width=800, height=600, color=(200, 100, 50)) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _import_real(session, storage, width=800, height=600):
    return image_service.import_engine_output(
        session, storage, data=_real_png(width, height), original_filename="a.png",
        source="comfyui",
    )


def _reject(session, storage, image, make_thumbnail=True):
    if make_thumbnail:
        thumbnail_service.get_or_create_thumbnail(session, storage, image)
    image_service.set_image_status(session, image.id, "REJECT")


def test_preview_does_not_delete_then_confirm_deletes(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    images = [_import_real(session, storage) for _ in range(3)]
    for image in images:
        _reject(session, storage, image)

    preview = cleanup_service.preview(session, storage)
    assert preview["candidate_count"] == 3
    assert preview["protected_count"] == 0
    assert preview["total_bytes"] > 0
    # 预览阶段绝不删除文件
    for image in images:
        assert storage.absolutize(image.file_path).is_file()

    result = cleanup_service.execute(session, storage)
    assert result["deleted_count"] == 3
    assert result["protected_count"] == 0
    assert result["deleted_bytes"] > 0
    # original 文件 + DB 记录都被删
    for image in images:
        assert not storage.absolutize(image.file_path).exists()
        with pytest.raises(NotFoundError):
            image_service.get_image(session, image.id)


def test_thumbnail_file_deleted_too(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import_real(session, storage)
    _reject(session, storage, image)  # 生成了 thumbnail

    variant = thumbnail_service.find_thumbnail_variant(session, image.id)
    thumb_path = storage.absolutize(variant.path)
    assert thumb_path.is_file()

    cleanup_service.execute(session, storage, [image.id])
    assert not thumb_path.exists(), "清理必须同时删除 thumbnail 文件"


def test_image_ids_limits_scope(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    images = [_import_real(session, storage) for _ in range(5)]
    for image in images:
        _reject(session, storage, image, make_thumbnail=False)

    target_ids = [images[1].id, images[3].id]
    result = cleanup_service.execute(session, storage, target_ids)
    assert result["deleted_count"] == 2
    # 其余三张 REJECT 不受影响
    assert storage.absolutize(images[0].file_path).is_file()
    assert storage.absolutize(images[2].file_path).is_file()
    assert storage.absolutize(images[4].file_path).is_file()


def test_non_reject_images_never_deleted(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    keep = _import_real(session, storage)
    image_service.set_image_status(session, keep.id, "KEEP")

    # 即便把 KEEP 图 id 传进 cleanup，也不得删除（只删 REJECT）
    result = cleanup_service.execute(session, storage, [keep.id])
    assert result["deleted_count"] == 0
    assert storage.absolutize(keep.file_path).is_file()


def test_preview_via_api(client, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(client.app.state.settings)
    with client.app.state.session_factory() as s:
        for _ in range(2):
            image = _import_real(s, storage)
            _reject(s, storage, image)

    preview = client.post("/api/v1/images/cleanup-rejected", json={"confirm": False}).json()
    assert preview["candidate_count"] == 2
    assert preview["protected_count"] == 0
    assert preview["total_bytes"] > 0

    confirmed = client.post("/api/v1/images/cleanup-rejected", json={"confirm": True}).json()
    assert confirmed["deleted_count"] == 2
