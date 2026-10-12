"""Phase 0.11.1 物理删除事务安全（trash staging）故障注入测试。

核心属性：任何 DB 删除失败都不得留下"DB 记录存在但原图文件已丢"的损坏状态。
- DB commit 失败 → 文件原子还原、Image/variant 行仍在；
- variant 移动失败 → 已移动的文件移回、DB 不动；
- original 缺失：部分文件存在走隔离区；全部文件缺失直接删 DB 行；
- 多张中一张失败不阻断其余；成功删除后隔离区被清空；protected 图不动。
"""
from __future__ import annotations

import io
import os
import time

import pytest
from PIL import Image as PILImage

from app.core.errors import NotFoundError
from app.models import Image, ImageVariant
from app.services import cleanup_service, image_service, thumbnail_service
from sqlalchemy import select


def _real_png(width=800, height=600, color=(200, 100, 50)) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _import_real(session, storage, width=800, height=600):
    return image_service.import_engine_output(
        session, storage, data=_real_png(width, height), original_filename="a.png",
        source="comfyui",
    )


def _reject_with_thumb(session, storage, image):
    thumbnail_service.get_or_create_thumbnail(session, storage, image)
    image_service.set_image_status(session, image.id, "REJECT")


def _variant_count(session, image_id):
    return len(list(session.execute(
        select(ImageVariant).where(ImageVariant.image_id == image_id)
    ).scalars().all()))


def test_db_commit_failure_restores_files_and_rows(session, settings, monkeypatch):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import_real(session, storage)
    _reject_with_thumb(session, storage, image)

    original_path = storage.absolutize(image.file_path)
    thumb = thumbnail_service.find_thumbnail_variant(session, image.id)
    thumb_path = storage.absolutize(thumb.path)
    assert original_path.is_file() and thumb_path.is_file()

    # 让 delete 内的 session.commit 抛错（故障注入）
    real_commit = session.commit
    def failing_commit():
        raise RuntimeError("injected commit failure")
    monkeypatch.setattr(session, "commit", failing_commit)

    result = cleanup_service.execute(session, storage, [image.id])
    # 恢复真实 commit，便于后续断言
    monkeypatch.setattr(session, "commit", real_commit)

    assert result["deleted_count"] == 0
    assert len(result["failed"]) == 1
    # 文件被原子还原，DB 行仍在 —— 不存在"DB 指向已丢文件"
    assert original_path.is_file()
    assert thumb_path.is_file()
    assert session.get(Image, image.id) is not None
    assert _variant_count(session, image.id) == 1


def test_one_failure_does_not_block_other_images(session, settings, monkeypatch):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    img1 = _import_real(session, storage)
    img2 = _import_real(session, storage)
    _reject_with_thumb(session, storage, img1)
    _reject_with_thumb(session, storage, img2)

    p1, p2 = storage.absolutize(img1.file_path), storage.absolutize(img2.file_path)

    # 第一次 commit 失败，之后恢复正常
    real_commit = session.commit
    calls = {"n": 0}
    def flaky_commit():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("injected first-commit failure")
        return real_commit()
    monkeypatch.setattr(session, "commit", flaky_commit)

    result = cleanup_service.execute(session, storage, [img1.id, img2.id])
    monkeypatch.setattr(session, "commit", real_commit)

    assert result["deleted_count"] == 1
    assert len(result["failed"]) == 1
    # 恰好一张被删、一张保留（证明失败不阻断其余）
    gone = [not p1.is_file(), not p2.is_file()]
    assert gone == [True, False] or gone == [False, True]
    if gone[0]:  # img1 被删
        assert session.get(Image, img1.id) is None
        assert session.get(Image, img2.id) is not None and p2.is_file()
    else:        # img2 被删
        assert session.get(Image, img2.id) is None
        assert session.get(Image, img1.id) is not None and p1.is_file()


def test_variant_move_failure_rolls_back_everything(session, settings, monkeypatch):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import_real(session, storage)
    _reject_with_thumb(session, storage, image)
    original_path = storage.absolutize(image.file_path)
    thumb = thumbnail_service.find_thumbnail_variant(session, image.id)
    thumb_path = storage.absolutize(thumb.path)

    real_move = storage.atomic_move_into
    def flaky_move(source, dest_dir, filename):
        if source.name == "thumbnail.webp":  # variant 移动失败
            raise OSError("injected variant move failure")
        return real_move(source, dest_dir, filename)
    monkeypatch.setattr(storage, "atomic_move_into", flaky_move)

    result = cleanup_service.execute(session, storage, [image.id])
    assert result["deleted_count"] == 0
    assert len(result["failed"]) == 1
    # original（已移入隔离区）被移回；thumbnail 从未移动；DB 行完整
    assert original_path.is_file()
    assert thumb_path.is_file()
    assert session.get(Image, image.id) is not None
    assert _variant_count(session, image.id) == 1


def test_original_missing_but_variant_exists_uses_staging_flow(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import_real(session, storage)
    _reject_with_thumb(session, storage, image)
    original_path = storage.absolutize(image.file_path)
    thumb = thumbnail_service.find_thumbnail_variant(session, image.id)
    thumb_path = storage.absolutize(thumb.path)

    # 历史异常：original 文件已丢，variant 还在
    os.unlink(original_path)
    assert not original_path.is_file() and thumb_path.is_file()

    result = cleanup_service.execute(session, storage, [image.id])
    assert result["deleted_count"] == 1
    assert not thumb_path.exists(), "variant 文件随隔离区被清除"
    with pytest.raises(NotFoundError):
        image_service.get_image(session, image.id)


def test_all_files_missing_deletes_db_rows_directly(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import_real(session, storage)
    _reject_with_thumb(session, storage, image)
    original_path = storage.absolutize(image.file_path)
    thumb = thumbnail_service.find_thumbnail_variant(session, image.id)
    thumb_path = storage.absolutize(thumb.path)

    # original 与所有 variant 文件都已丢失
    os.unlink(original_path)
    os.unlink(thumb_path)

    result = cleanup_service.execute(session, storage, [image.id])
    assert result["deleted_count"] == 1
    assert result["deleted_bytes"] == 0
    with pytest.raises(NotFoundError):
        image_service.get_image(session, image.id)


def test_protected_image_not_touched(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    protected = _import_real(session, storage)
    _reject_with_thumb(session, storage, protected)
    # 派生图挂在 protected 下 → 产生引用
    child = _import_real(session, storage)
    child.parent_image_id = protected.id
    session.commit()

    original_path = storage.absolutize(protected.file_path)
    result = cleanup_service.execute(session, storage, [protected.id])
    assert result["protected_count"] == 1
    assert result["deleted_count"] == 0
    assert original_path.is_file()
    assert session.get(Image, protected.id) is not None


def test_successful_delete_clears_staging(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import_real(session, storage)
    _reject_with_thumb(session, storage, image)
    original_path = storage.absolutize(image.file_path)

    result = cleanup_service.execute(session, storage, [image.id])
    assert result["deleted_count"] == 1
    assert not original_path.exists()
    with pytest.raises(NotFoundError):
        image_service.get_image(session, image.id)

    # 隔离区不得残留任何文件（空目录可被 stale 清理回收）
    staging_base = storage.resolve_under("images/temp", "delete_staging")
    if staging_base.is_dir():
        leftovers = [p for p in staging_base.rglob("*") if p.is_file()]
        assert leftovers == []


def test_cleanup_stale_staging_removes_old_dirs(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    old_dir = storage.resolve_under("images/temp", "delete_staging", "fakecleanup", "img_old")
    old_dir.mkdir(parents=True, exist_ok=True)
    (old_dir / "stale.bin").write_bytes(b"x")
    # 置为很久以前的 mtime
    old_time = time.time() - 10 * 86400
    os.utime(old_dir, (old_time, old_time))

    removed = cleanup_service.cleanup_stale_staging(storage, retention_seconds=0)
    assert removed >= 1
    staging_base = storage.resolve_under("images/temp", "delete_staging")
    leftovers = [p for p in staging_base.rglob("*") if p.is_file()] if staging_base.is_dir() else []
    assert leftovers == []
