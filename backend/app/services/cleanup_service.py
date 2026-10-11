"""废片清理（Phase 0.11：REJECT 两阶段 —— 预览 → 确认删除）。

流程（合同冻结 API #5）：
- NEW → REJECT 只是标记，**不立即删除**；只有用户在「清理废片」弹窗点确认才真删；
- 候选 = status=REJECT 的图（image_ids 给定时限定为其中 REJECT 的；不给则全库 REJECT）；
- 删除前**逐张复用 ImageReferenceService.count_references**：被 Prompt / Asset / Recipe /
  派生图 / 活跃 Job / Asset 溯源引用（total>0）的图**跳过并计入 protected**，绝不留悬空；
- confirm != true → 仅预览 {candidate_count, total_bytes, protected_count}（total_bytes 为
  预计释放 = 可删图的 original+全部 variants 磁盘字节）；
- confirm == true → 真删：删除 original + 全部 variants(含 thumbnail) 文件 + variant 行 +
  Image 行，并清空指向本图的 job 输出指针（job_items.image_id / job_stage_items.output_image_id），
  返回 {deleted_count, deleted_bytes, protected_count, failed[]}。
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import Image, ImageVariant, JobItem, JobStageItem
from app.services import image_reference_service
from app.storage.manager import StorageManager


def _candidates(session: Session, image_ids: list[str] | None) -> list[Image]:
    query = select(Image).where(Image.status == "REJECT")
    if image_ids:
        query = query.where(Image.id.in_(image_ids))
    return list(session.execute(query).scalars().all())


def _list_variants(session: Session, image_id: str) -> list[ImageVariant]:
    return list(session.execute(
        select(ImageVariant).where(ImageVariant.image_id == image_id)
    ).scalars().all())


def _image_disk_bytes(session: Session, storage: StorageManager, image: Image) -> int:
    """original + 全部 variants 文件字节（文件缺失按 0 计）。"""
    total = 0
    original = storage.absolutize(image.file_path)
    if original.is_file():
        total += original.stat().st_size
    for variant in _list_variants(session, image.id):
        path = storage.absolutize(variant.path)
        if path.is_file():
            total += path.stat().st_size
    return total


def preview(session: Session, storage: StorageManager,
            image_ids: list[str] | None = None) -> dict:
    """两阶段之一：只统计不删除。protected 图不计入预计释放字节。"""
    candidates = _candidates(session, image_ids)
    total_bytes = 0
    protected_count = 0
    for image in candidates:
        refs = image_reference_service.count_references(session, image.id)
        if refs["total"] > 0:
            protected_count += 1
            continue
        total_bytes += _image_disk_bytes(session, storage, image)
    return {
        "candidate_count": len(candidates),
        "total_bytes": total_bytes,
        "protected_count": protected_count,
    }


def _delete_one(session: Session, storage: StorageManager, image: Image) -> int:
    """删除单张未受保护图的文件 + DB 记录，返回释放字节数。

    DB 删除按外键依赖顺序显式执行（image_variants→images 无 ORM 关系，
    不能依赖 unit-of-work 自动排序，否则 DELETE images 会撞外键约束）。
    """
    freed = _image_disk_bytes(session, storage, image)

    # 1) 文件：original + 全部 variants（含 thumbnail）
    original_abs = storage.absolutize(image.file_path)
    storage.safe_delete(original_abs)
    # 删除 now-empty 的 per-image 目录（仅当为空且目录名即本图 id，绝不误删 originals 根）
    try:
        parent = original_abs.parent
        if parent.name == image.id and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass
    for variant in _list_variants(session, image.id):
        storage.safe_delete(storage.absolutize(variant.path))

    # 2) 清空指向本图的 job 输出指针，避免 job 侧悬空 image_id
    session.execute(update(JobItem).where(JobItem.image_id == image.id).values(image_id=None))
    session.execute(
        update(JobStageItem).where(JobStageItem.output_image_id == image.id)
        .values(output_image_id=None)
    )
    # 3) 显式先删 image_variants 行，再删 Image 行（外键依赖顺序）
    session.execute(delete(ImageVariant).where(ImageVariant.image_id == image.id))
    session.execute(delete(Image).where(Image.id == image.id))
    session.commit()
    return freed


def execute(session: Session, storage: StorageManager,
            image_ids: list[str] | None = None) -> dict:
    """两阶段之二：真删未受保护的 REJECT 图。"""
    candidates = _candidates(session, image_ids)
    deleted_count = 0
    deleted_bytes = 0
    protected_count = 0
    failed: list[dict] = []
    for image in candidates:
        refs = image_reference_service.count_references(session, image.id)
        if refs["total"] > 0:
            protected_count += 1
            continue
        try:
            freed = _delete_one(session, storage, image)
            deleted_count += 1
            deleted_bytes += freed
        except Exception as error:  # noqa: BLE001 —— 单张失败不阻断其余
            session.rollback()
            failed.append({
                "image_id": image.id,
                "error_code": getattr(error, "code", "DELETE_FAILED"),
                "message": str(error),
            })
    return {
        "deleted_count": deleted_count,
        "deleted_bytes": deleted_bytes,
        "protected_count": protected_count,
        "failed": failed,
    }
