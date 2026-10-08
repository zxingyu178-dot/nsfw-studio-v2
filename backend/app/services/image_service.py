"""ImageService（Phase 2C，规范 §三十九、§四十、§四十一-§四十三；Phase 3 §十四 泛化）。

引擎输出导入流程（规范 §四十）::

    Engine 输出字节 → Studio temp → 校验（magic bytes + 尺寸解析）
    → 原子移动到 DataRoot/images/<kind 目录>/<img_id>/ → Image DB 登记

kind 决定存储目录（original→images/originals / upscaled→images/upscaled /
processed→images/processed）；高清图必须记录 parent_image_id（§十四）。

ComfyUI output 目录不作为 Studio 永久图库；数据库只存 DataRoot 相对路径。
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.filetypes import image_dimensions, mime_for_suffix, sniff_image_format
from app.core.ids import IMAGE, new_id
from app.engine.base import EngineOutputFile
from app.models import Image, Job, JobItem, JobStage, JobStageItem
from app.storage.manager import StorageManager
from app.workflows.base import InputImageRef

IMAGE_SOURCES = ("comfyui", "mock", "import")
IMAGE_KIND_DIRS = {
    "original": "images/originals",
    "upscaled": "images/upscaled",
    "processed": "images/processed",
}


def _kind_dir(kind: str) -> str:
    directory = IMAGE_KIND_DIRS.get(kind)
    if directory is None:
        raise ValidationError(f"非法图片 kind: {kind}", code="IMAGE_KIND_INVALID")
    return directory


def get_image(session: Session, image_id: str) -> Image:
    image = session.get(Image, image_id)
    if image is None:
        raise NotFoundError("图片不存在", code="IMAGE_NOT_FOUND")
    return image


def get_versions(session: Session, image_id: str) -> dict[str, Any]:
    """父子关系（§十九）：返回 {image, parent, children}，支持原图/高清之间切换。"""
    image = get_image(session, image_id)
    parent = session.get(Image, image.parent_image_id) if image.parent_image_id else None
    children = list(session.execute(
        select(Image).where(Image.parent_image_id == image_id).order_by(Image.created_at)
    ).scalars())
    return {"image": image, "parent": parent, "children": children}


@dataclass(frozen=True)
class PreparedImageOutput:
    """已校验、已分配身份的待导入输出（尚未落盘/入库）。"""

    image_id: str
    data: bytes
    suffix: str
    relative_path: str
    width: int
    height: int


def prepare_image_output(data: bytes, *, kind: str = "original") -> PreparedImageOutput:
    """校验输出字节并生成 Image 身份与元数据（不落盘、不入库）。

    Phase 2.2 §1：整批导入必须先对全部输出做本步骤，任一不合法即整批失败，
    绝不允许"先落了一张、后一张校验失败"的半成功状态。
    Phase 3 §十四：kind 决定正式目录（original/upscaled/processed）。
    """
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
    directory = _kind_dir(kind)
    return PreparedImageOutput(
        image_id=image_id,
        data=data,
        suffix=suffix,
        relative_path=f"{directory}/{image_id}/{kind}{suffix}",
        width=width,
        height=height,
    )


def import_outputs_transaction(
    session: Session,
    storage: StorageManager,
    prepared: list[PreparedImageOutput],
    *,
    job: Job | None = None,
    item: JobItem | None = None,
    seed: int | None = None,
    source: str = "comfyui",
    kind: str = "original",
    parent_image_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[Image]:
    """一个输出批次"整体成功或整体失败"导入（Phase 2.2 §1，P0）。

    顺序：全部写 temp → 全部移动到正式目录 → 单事务写入全部 Image → commit。
    任一步失败：回滚 DB + 删除本批次已创建的全部正式文件 + 清理 temp。
    禁止在批次循环里调用任何内部 commit 的单图函数。
    """
    if source not in IMAGE_SOURCES:
        raise ValidationError(f"非法图片来源: {source}", code="IMAGE_SOURCE_INVALID")
    directory = _kind_dir(kind)
    if not prepared:
        return []

    temp_paths: list[Path] = []
    created_dirs: list[Path] = []
    try:
        storage.temp_dir.mkdir(parents=True, exist_ok=True)
        # 1. 全部写 temp（尚未接触正式目录）
        for entry in prepared:
            temp_path = storage.temp_dir / f"import_{uuid.uuid4().hex}{entry.suffix}"
            temp_path.write_bytes(entry.data)
            temp_paths.append(temp_path)
        # 2. 全部移动到正式目录（kind → images/originals|upscaled|processed）
        for entry, temp_path in zip(prepared, temp_paths):
            final_dir = storage.resolve_under(directory, entry.image_id)
            final_dir.mkdir(parents=True, exist_ok=True)
            created_dirs.append(final_dir)
            storage.atomic_move_into(temp_path, final_dir, f"{kind}{entry.suffix}")
        # 3. 单事务写入全部 Image
        images = [
            Image(
                id=entry.image_id,
                job_id=job.id if job is not None else None,
                job_item_id=item.id if item is not None else None,
                parent_image_id=parent_image_id,
                kind=kind,
                file_path=entry.relative_path,
                width=entry.width,
                height=entry.height,
                seed=seed,
                review_status="UNREVIEWED",
                favorite=False,
                source=source,
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            )
            for entry in prepared
        ]
        for image in images:
            session.add(image)
        session.commit()
        return images
    except Exception:
        session.rollback()
        for path in temp_paths:
            storage.safe_delete(path)
        for directory in created_dirs:
            storage.safe_delete(directory)
        raise


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
    """单图便捷入口（prepare + 单元素批次事务）。

    仅供单张场景；多图必须走 prepare_image_output() + import_outputs_transaction()
    的整批路径（Phase 2.2 §1）。original_filename 仅作调用签名兼容，不参与落盘命名。
    """
    prepared = prepare_image_output(data, kind=kind)
    images = import_outputs_transaction(
        session, storage, [prepared],
        job=job, item=item, seed=seed, source=source, kind=kind, metadata=metadata,
    )
    return images[0]


def import_adapter_outputs(session: Session, storage: StorageManager, job: Job,
                           stage_item: JobStageItem, outputs: list[EngineOutputFile]) -> list[str]:
    """Worker 的 output_importer 回调：把 Adapter 取回的输出登记为 Image（Phase 3 §十四）。

    kind 由 StageItem 判定：有 input_image_id（处理/放大阶段）→ upscaled + parent_image_id；
    否则 → original。Phase 2.2 §1：先全部校验（prepare）→ 整批事务导入。
    """
    stage = session.get(JobStage, stage_item.job_stage_id) if stage_item is not None else None
    job_item = session.get(JobItem, stage_item.job_item_id) if stage_item is not None else None
    has_input = bool(stage_item is not None and stage_item.input_image_id)
    kind = "upscaled" if has_input else "original"
    parent_image_id = stage_item.input_image_id if has_input else None
    source = "comfyui" if job.provider == "comfyui" else ("mock" if job.provider == "mock" else "import")
    metadata = {
        "module_id": stage.module_id if stage is not None else job.module_id,
        "module_version": stage.module_version if stage is not None else job.module_version,
        "provider": stage.provider if stage is not None else job.provider,
        "binding_version": stage.binding_version if stage is not None else job.binding_version,
        "workflow_hash": stage.workflow_hash if stage is not None else job.workflow_hash,
        "stage_id": stage.id if stage is not None else None,
        "stage_index": stage.stage_index if stage is not None else None,
        "stage_item_id": stage_item.id if stage_item is not None else None,
        "parent_image_id": parent_image_id,
        "actual_provider": job.provider,
    }
    prepared = [prepare_image_output(output.data, kind=kind) for output in outputs]
    images = import_outputs_transaction(
        session, storage, prepared,
        job=job, item=job_item, seed=job_item.seed if job_item is not None else None,
        source=source, kind=kind, parent_image_id=parent_image_id, metadata=metadata,
    )
    return [image.id for image in images]


def load_input_image_ref(session: Session, storage: StorageManager, image_id: str) -> InputImageRef:
    """加载处理型 Stage 的输入图片（§十三/§二十一）→ InputImageRef（字节已在内存）。"""
    image = get_image(session, image_id)
    path = storage.absolutize(image.file_path)
    if not path.is_file():
        raise NotFoundError("输入图片文件不存在", code="IMAGE_FILE_MISSING")
    return InputImageRef(
        image_id=image.id,
        file_name=path.name,
        data=path.read_bytes(),
        width=image.width,
        height=image.height,
    )


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
