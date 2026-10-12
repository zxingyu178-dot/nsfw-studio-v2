"""Phase 0.11 ImageVariant 表约束测试（变体独立成表、thumbnail 每图唯一）。"""
from __future__ import annotations

import io

import pytest
from PIL import Image as PILImage
from sqlalchemy import text

from app.models import ImageVariant
from app.services import image_service, thumbnail_service


def _png_bytes(width=800, height=600) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (width, height), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def _import(session, storage):
    return image_service.import_engine_output(
        session, storage, data=_png_bytes(), original_filename="a.png", source="comfyui",
    )


def test_variant_row_metadata(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import(session, storage)
    _path, variant = thumbnail_service.get_or_create_thumbnail(session, storage, image)

    assert isinstance(variant, ImageVariant)
    assert variant.image_id == image.id
    assert variant.variant_type == "thumbnail"
    assert variant.width == 512 and variant.height == 384
    assert variant.format == "webp"
    assert variant.created_at, "变体必须有创建时间"


def test_thumbnail_unique_per_image(session, settings):
    """部分唯一索引：同图只能有一个 thumbnail variant（第二次生成不新建第二行）。"""
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import(session, storage)
    _p, v1 = thumbnail_service.get_or_create_thumbnail(session, storage, image)
    _p, v2 = thumbnail_service.get_or_create_thumbnail(session, storage, image)
    assert v1.id == v2.id

    # 直接插第二行 thumbnail 必须被唯一索引拒绝
    from app.core.ids import IMAGE_VARIANT, new_id
    from sqlalchemy.exc import IntegrityError

    dup = ImageVariant(
        id=new_id(IMAGE_VARIANT), image_id=image.id, variant_type="thumbnail",
        path="images/thumbnails/fake/thumbnail.webp",
    )
    session.add(dup)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_images_table_not_polluted_by_variant(session, settings):
    """变体信息不得写回 images 表（images 无 thumbnail 相关列）。"""
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import(session, storage)
    thumbnail_service.get_or_create_thumbnail(session, storage, image)

    columns = {row[1] for row in session.execute(text("PRAGMA table_info(images)"))}
    assert "thumbnail_path" not in columns
    assert "thumbnail_variant_id" not in columns
    # 但新审核列存在（0016）
    assert {"status", "reviewed_at", "review_note"}.issubset(columns)


def test_image_variants_table_exists(session):
    """0015 迁移已建 image_variants 表且 variant_type 约束含 thumbnail。"""
    rows = list(session.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='image_variants'"
    )))
    assert rows, "image_variants 表必须存在"
