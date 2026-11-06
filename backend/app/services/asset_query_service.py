"""W4.1 AssetQueryService：图片资产统计、缺失/孤立识别与统一投影。

只读：不删除孤立文件、不修改图片记录。孤立文件只进入报告，等待人工确认。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Image, ImageVariant
from app.storage.manager import StorageManager


def _asset_type(image: Image) -> str:
    """W4.1 资产类型：original / processed / upscaled(历史) / imported / other_variant。"""
    if image.source == "import":
        return "imported"
    if image.kind in ("original", "processed", "upscaled"):
        return image.kind
    return "other_variant"


def image_asset_view(image: Image) -> dict[str, Any]:
    """把 Image ORM 投影为 W4.1 统一资产字段（不新增重复表）。"""
    import json

    metadata = {}
    try:
        metadata = json.loads(image.metadata_json or "{}")
    except ValueError:
        metadata = {}
    imported = image.source == "import"
    return {
        "asset_id": image.id,
        "storage_key": image.file_path,
        "sha256": image.sha256,
        "mime_type": metadata.get("mime_type") or _mime_from_suffix(image.file_path),
        "width": image.width,
        "height": image.height,
        "file_size": metadata.get("file_size"),
        "asset_type": _asset_type(image),
        "parent_asset_id": image.parent_image_id,
        "job_id": image.job_id,
        "generation_item_id": image.job_item_id,
        "seed": image.seed,
        "review_status": image.status,
        "favorite": bool(image.favorite),
        "created_at": image.created_at,
        # 外部导入图本来就没有 Job 关联，不属于"历史缺失关联"。
        "legacy": image.job_id is None and not imported,
        "unlinked": image.job_id is None and not imported,
    }


def _mime_from_suffix(path: str) -> str | None:
    suffix = Path(path).suffix.lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix)


def stats(session: Session, storage: StorageManager, *, check_files: bool = True) -> dict[str, Any]:
    """资产完整性统计。``check_files`` 会逐条 stat（7k+ 文件，约 1 秒）。"""
    total = session.execute(select(func.count()).select_from(Image)).scalar_one()
    by_kind = dict(session.execute(select(Image.kind, func.count()).group_by(Image.kind)).all())
    by_source = dict(session.execute(select(Image.source, func.count()).group_by(Image.source)).all())
    by_status = dict(session.execute(select(Image.status, func.count()).group_by(Image.status)).all())
    with_parent = session.execute(
        select(func.count()).select_from(Image).where(Image.parent_image_id.is_not(None))
    ).scalar_one()
    with_job = session.execute(
        select(func.count()).select_from(Image).where(Image.job_id.is_not(None))
    ).scalar_one()
    with_sha = session.execute(
        select(func.count()).select_from(Image).where(Image.sha256.is_not(None))
    ).scalar_one()

    variants = session.execute(select(func.count()).select_from(ImageVariant)).scalar_one()
    variant_types = dict(session.execute(
        select(ImageVariant.variant_type, func.count()).group_by(ImageVariant.variant_type)
    ).all())
    with_thumbnail = session.execute(text(
        "SELECT count(DISTINCT image_id) FROM image_variants WHERE variant_type = 'thumbnail'"
    )).scalar_one()
    with_prompt = session.execute(text("""
        SELECT count(*) FROM images i
        WHERE (
          i.job_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM jobs j
            WHERE j.id = i.job_id
              AND json_extract(j.workbench_snapshot_json, '$.source_prompt_id') IS NOT NULL
          )
        ) OR (
          i.source = 'import'
          AND json_array_length(COALESCE(json_extract(i.metadata_json, '$.v1_output.prompts'), '[]')) > 0
        )
    """)).scalar_one()

    missing_images: list[dict[str, Any]] = []
    missing_variants: list[dict[str, Any]] = []
    missing_thumbnails: list[dict[str, Any]] = []
    if check_files:
        for image in session.execute(select(Image)).scalars():
            if not storage.absolutize(image.file_path).is_file():
                missing_images.append({"asset_id": image.id, "storage_key": image.file_path})
        for variant in session.execute(select(ImageVariant)).scalars():
            if not storage.absolutize(variant.path).is_file():
                missing_variants.append({
                    "variant_id": variant.id, "asset_id": variant.image_id,
                    "variant_type": variant.variant_type, "path": variant.path,
                })
                if variant.variant_type == "thumbnail":
                    missing_thumbnails.append({
                        "variant_id": variant.id, "asset_id": variant.image_id, "path": variant.path,
                    })

    return {
        "total": total,
        "by_kind": by_kind,
        "by_source": by_source,
        "by_status": by_status,
        "with_parent": with_parent,
        "with_job": with_job,
        "without_job": total - with_job,
        "with_sha256": with_sha,
        "missing_sha256": total - with_sha,
        "variants_total": variants,
        "variants_by_type": variant_types,
        "images_with_thumbnail": with_thumbnail,
        "images_without_thumbnail": total - with_thumbnail,
        "thumbnails_missing": len(missing_thumbnails),
        "thumbnails_missing_samples": missing_thumbnails[:20],
        "with_prompt": with_prompt,
        "without_prompt": total - with_prompt,
        "missing_files": len(missing_images),
        "missing_file_samples": missing_images[:20],
        "missing_variant_files": len(missing_variants),
        "missing_variant_samples": missing_variants[:20],
        "files_checked": check_files,
    }


def orphan_files(storage: StorageManager, known_keys: set[str], *, roots: tuple[str, ...] = (
    "assets/images", "images/originals", "images/upscaled", "images/processed",
    "cache/thumbnails", "cache/previews",
)) -> list[dict[str, Any]]:
    """扫描物理文件但数据库未登记的孤立资产（只报告，不删除）。"""
    orphans: list[dict[str, Any]] = []
    for root in roots:
        base = storage.absolutize(root)
        if not base.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            for name in filenames:
                path = Path(dirpath) / name
                rel = storage.relative_to_root(path)
                if rel not in known_keys:
                    orphans.append({"path": rel, "size": path.stat().st_size})
    return orphans
