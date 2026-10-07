"""ImageService（Phase 2C，规范 §三十九、§四十、§四十一-§四十三）。

引擎输出导入流程（规范 §四十）::

    Engine 输出字节 → Studio temp → 校验（magic bytes + 尺寸解析）
    → 原子移动到 DataRoot/images/originals/<img_id>/ → Image DB 登记

ComfyUI output 目录不作为 Studio 永久图库；数据库只存 DataRoot 相对路径。
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.filetypes import image_dimensions, mime_for_suffix, sniff_image_format
from app.core.ids import IMAGE, new_id
from app.engine.base import EngineOutputFile
from app.models import Image, Job, JobItem
from app.storage.manager import StorageManager

IMAGE_SOURCES = ("comfyui", "mock", "import")


def get_image(session: Session, image_id: str) -> Image:
    image = session.get(Image, image_id)
    if image is None:
        raise NotFoundError("图片不存在", code="IMAGE_NOT_FOUND")
    return image


def import_engine_output(
    session: Session,
    storage: StorageManager,
    *,
    data: bytes,
    original_filename: str,
    job: Job | None = None,
    item: JobItem | None = None,
    seed: int | None = None,
    source: str = "comfyui",
    kind: str = "original",
    metadata: dict[str, Any] | None = None,
) -> Image:
    """把单个引擎输出导入为正式 Studio Image（规范 §四十，失败任一步全回滚）。"""
    if source not in IMAGE_SOURCES:
        raise ValidationError(f"非法图片来源: {source}", code="IMAGE_SOURCE_INVALID")
    if not data:
        raise ValidationError("输出文件为空", code="OUTPUT_MISSING")
    fmt = sniff_image_format(data)
    if fmt is None:
        raise ValidationError("引擎输出不是可识别的图片", code="OUTPUT_MISSING")
    dimensions = image_dimensions(data)
    if dimensions is None:
        raise ValidationError("无法解析图片尺寸", code="OUTPUT_MISSING")
    width, height = dimensions

    suffix = ".png" if fmt == "png" else (".jpg" if fmt == "jpeg" else ".webp")
    image_id = new_id(IMAGE)
    final_dir = storage.resolve_under("images/originals", image_id)
    relative_target = f"images/originals/{image_id}/original{suffix}"

    temp_path = storage.temp_dir / f"import_{uuid.uuid4().hex}{suffix}"
    storage.temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path.write_bytes(data)
    try:
        final_dir.mkdir(parents=True, exist_ok=True)
        moved = storage.atomic_move_into(temp_path, final_dir, f"original{suffix}")
    except Exception:
        storage.safe_delete(temp_path)
        storage.safe_delete(final_dir)
        raise

    image = Image(
        id=image_id,
        job_id=job.id if job is not None else None,
        job_item_id=item.id if item is not None else None,
        kind=kind,
        file_path=relative_target,
        width=width,
        height=height,
        seed=seed,
        review_status="UNREVIEWED",
        favorite=False,
        source=source,
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
    )
    try:
        session.add(image)
        session.commit()
    except Exception:
        session.rollback()
        storage.safe_delete(storage.resolve_under("images/originals", image_id))
        raise
    return image


def import_adapter_outputs(session: Session, storage: StorageManager, job: Job, item: JobItem, outputs: list[EngineOutputFile]) -> list[str]:
    """Worker 的 output_importer 回调：把 Adapter 取回的输出文件登记为 Image。"""
    source = "comfyui" if job.provider == "comfyui" else ("mock" if job.provider == "mock" else "import")
    metadata = {
        "module_id": job.module_id,
        "module_version": job.module_version,
        "provider": job.provider,
        "binding_version": job.binding_version,
        "workflow_hash": job.workflow_hash,
        "actual_provider": job.provider,
    }
    image_ids: list[str] = []
    for output in outputs:
        image = import_engine_output(
            session, storage,
            data=output.data,
            original_filename=output.filename,
            job=job, item=item,
            seed=item.seed,
            source=source,
            metadata=metadata,
        )
        image_ids.append(image.id)
    return image_ids


def list_images(
    session: Session,
    *,
    job_id: str | None = None,
    review_status: str | None = None,
    favorite: bool | None = None,
    source: str | None = None,
    kind: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Image], int]:
    if limit < 1 or limit > 200:
        raise ValidationError("limit 取值范围为 1-200")
    if offset < 0:
        raise ValidationError("offset 不能为负")
    if review_status is not None and review_status not in ("UNREVIEWED", "KEPT", "REJECTED"):
        raise ValidationError(f"非法审核状态: {review_status}", code="REVIEW_STATUS_INVALID")

    query = select(Image)
    if job_id is not None:
        query = query.where(Image.job_id == job_id)
    if review_status is not None:
        query = query.where(Image.review_status == review_status)
    if favorite is not None:
        query = query.where(Image.favorite == favorite)
    if source is not None:
        query = query.where(Image.source == source)
    if kind is not None:
        query = query.where(Image.kind == kind)
    if date_from is not None:
        query = query.where(Image.created_at >= date_from)
    if date_to is not None:
        query = query.where(Image.created_at <= date_to)

    total = session.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    items = list(session.execute(query.order_by(Image.created_at.desc()).limit(limit).offset(offset)).scalars())
    return items, int(total)


def set_review(session: Session, image_id: str, review_status: str) -> Image:
    if review_status not in ("UNREVIEWED", "KEPT", "REJECTED"):
        raise ValidationError(f"非法审核状态: {review_status}", code="REVIEW_STATUS_INVALID")
    image = get_image(session, image_id)
    image.review_status = review_status
    session.commit()
    return image


def set_favorite(session: Session, image_id: str, favorite: bool) -> Image:
    image = get_image(session, image_id)
    image.favorite = favorite
    session.commit()
    return image


def job_gallery_summary(session: Session, job_id: str) -> dict:
    """按 Job 统计（规范 §四十九：未审核 / 保留 / 收藏 / 淘汰）。"""
    rows = session.execute(
        select(Image.review_status, func.count())
        .where(Image.job_id == job_id)
        .group_by(Image.review_status)
    ).all()
    counts = {status: int(count) for status, count in rows}
    favorites = session.execute(
        select(func.count()).select_from(Image)
        .where(Image.job_id == job_id, Image.favorite.is_(True))
    ).scalar_one()
    return {
        "job_id": job_id,
        "total": sum(counts.values()),
        "unreviewed": counts.get("UNREVIEWED", 0),
        "kept": counts.get("KEPT", 0),
        "rejected": counts.get("REJECTED", 0),
        "favorites": int(favorites),
    }
