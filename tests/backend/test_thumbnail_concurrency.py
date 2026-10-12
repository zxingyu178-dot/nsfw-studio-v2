"""Phase 0.11.1 P1-4：thumbnail/preview 生产链并发安全测试。

- 线程池并发对同一图 get_or_create 只产生 1 个 variant、不抛异常；
- 正式文件存在且非临时/半写（无 .tmp 残留、可被 Pillow 打开）；
- 模拟 INSERT IntegrityError 后 re-read 成功；
- preview 与 thumbnail 互不干扰。
"""
from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image as PILImage
from sqlalchemy.exc import IntegrityError

from app.models import Image
from app.services import image_service, thumbnail_service


def _png_bytes(width: int, height: int, color=(120, 80, 200)) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _import(session, storage, width=1024, height=768):
    return image_service.import_engine_output(
        session, storage, data=_png_bytes(width, height), original_filename="a.png",
        source="comfyui",
    )


def _dir_of(storage, image_id: str, variant_type: str):
    spec = thumbnail_service.VARIANT_SPECS[variant_type]
    return storage.resolve_under(spec.directory, image_id)


def test_concurrent_get_or_create_single_variant(session_factory, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image_id: str | None = None
    with session_factory() as s:
        image = _import(s, storage)
        image_id = image.id

    def worker(_):
        with session_factory() as s:
            img = s.get(Image, image_id)
            _path, variant = thumbnail_service.get_or_create_thumbnail(s, storage, img)
            return variant.id

    with ThreadPoolExecutor(max_workers=8) as pool:
        variant_ids = list(pool.map(worker, range(12)))

    # 全部成功、不抛异常；最终只落一个 thumbnail variant 行
    assert all(v is not None for v in variant_ids)
    assert len(set(variant_ids)) == 1, f"并发只应产生 1 个 variant，实得: {set(variant_ids)}"
    with session_factory() as s:
        assert thumbnail_service.find_thumbnail_variant(s, image_id) is not None


def test_no_temp_residue_and_valid_webp(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import(session, storage, 900, 700)
    path, variant = thumbnail_service.get_or_create_thumbnail(session, storage, image)

    assert path.is_file()
    target_dir = _dir_of(storage, image.id, "thumbnail")
    leftovers = [p.name for p in target_dir.iterdir() if p.name.startswith(".tmp-")]
    assert leftovers == [], f"不应残留临时文件: {leftovers}"
    # 正式文件可被 Pillow 打开（非半写 WebP）
    with PILImage.open(path) as im:
        assert im.format == "WEBP"
        im.load()


def test_integrity_error_triggers_reread(session, settings, monkeypatch):
    """第一次 INSERT 抛 IntegrityError → 回滚后 re-read 已存在行成功（不抛 500）。"""
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import(session, storage)
    # 入库已自动生成 thumbnail：先删掉 variant 行 + 文件，制造"首次 INSERT"条件
    existing = thumbnail_service.find_thumbnail_variant(session, image.id)
    storage.absolutize(existing.path).unlink()
    session.delete(existing)
    session.commit()

    real_commit = session.commit
    calls = {"n": 0}

    def flaky_commit():
        calls["n"] += 1
        if calls["n"] == 1:
            # 模拟"另一事务已插入同图 thumbnail"：先由真实路径落一个 variant 行，
            # 再抛 IntegrityError，触发 collision re-read 分支。
            real_commit()
            raise IntegrityError("INSERT", {}, Exception("uq_image_variants_thumbnail"))
        return real_commit()

    monkeypatch.setattr(session, "commit", flaky_commit)
    path, variant = thumbnail_service.get_or_create_thumbnail(session, storage, image)
    assert path.is_file()
    assert variant.variant_type == "thumbnail"
    assert calls["n"] >= 1


def test_preview_and_thumbnail_independent(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import(session, storage, 1400, 1050)

    t_path, t_variant = thumbnail_service.get_or_create_thumbnail(session, storage, image)
    p_path, p_variant = thumbnail_service.get_or_create_preview(session, storage, image)

    assert t_variant.variant_type == "thumbnail"
    assert p_variant.variant_type == "preview"
    assert t_variant.id != p_variant.id
    # preview 长边 1536：1400x1050 → 最长边 1400 < 1536，保持原尺寸不放大小图
    assert (p_variant.width, p_variant.height) == (1400, 1050)
    # thumbnail 长边 512：1400x1050 → 512x384
    assert (t_variant.width, t_variant.height) == (512, 384)
    # 目录互不干扰
    assert "images/thumbnails/" in t_variant.path
    assert "images/previews/" in p_variant.path
    with PILImage.open(p_path) as im:
        assert im.format == "WEBP"


def test_preview_downscales_large_image(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import(session, storage, 2048, 1536)  # 长边 2048 > 1536

    _p_path, p_variant = thumbnail_service.get_or_create_preview(session, storage, image)
    # 长边下采样到 1536，另一边 1536*1536/2048=1152
    assert (p_variant.width, p_variant.height) == (1536, 1152)
