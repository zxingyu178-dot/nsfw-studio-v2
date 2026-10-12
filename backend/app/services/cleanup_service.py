"""废片清理（Phase 0.11：REJECT 两阶段 —— 预览 → 确认删除）。

流程（合同冻结 API #5）：
- NEW → REJECT 只是标记，**不立即删除**；只有用户在「清理废片」弹窗点确认才真删；
- 候选 = status=REJECT 的图（image_ids 给定时限定为其中 REJECT 的；不给则全库 REJECT）；
- 删除前**逐张复用 ImageReferenceService.count_references**：被 Prompt / Asset / Recipe /
  派生图 / 活跃 Job / Asset 溯源引用（total>0）的图**跳过并计入 protected**，绝不留悬空；
- confirm != true → 仅预览 {candidate_count, total_bytes, protected_count}（total_bytes 为
  预计释放 = 可删图的 original+全部 variants 磁盘字节）；
- confirm == true → 真删，返回 {deleted_count, deleted_bytes, protected_count, failed[]}。

Phase 0.11.1（P0-3）物理删除事务安全 —— trash staging 隔离区：
- 先把 original + 全部 variants 用 ``os.replace``（storage.atomic_move_into，同卷原子）
  移到 ``images/temp/delete_staging/<cleanup_id>/<image_id>/``，再开 DB 事务删行；
- DB commit 成功后才物理清除隔离区；commit 失败 → rollback 并把文件原子移回原路径；
- **绝不**用吞 OSError 的 safe_delete 做关键删除步骤（safe_delete 仅用于成功后的隔离区
  purge 与空目录清理，以及回滚收尾）；
- 杜绝"DB 有记录文件没了"：文件移动失败则 DB 不动并移回；DB 失败则文件还原。
"""
from __future__ import annotations

import logging
import shutil
import time
import uuid
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import Image, ImageVariant, JobItem, JobStageItem
from app.services import image_reference_service
from app.storage.manager import StorageManager

logger = logging.getLogger(__name__)

# 启动/维护清理超过该时长的 delete_staging 残留目录（秒）
STALE_STAGING_RETENTION_SECONDS = 24 * 60 * 60


class _DeleteAborted(Exception):
    """单张删除中途中止：文件已原子移回原路径（或本就未动），DB 记录保持不变。"""


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


# count_references 返回的引用分类键 → protected 原因摘要（按服务实际返回的键名派生）
_REASON_KEYS = {
    "prompt_preview_ids": "prompt_preview",
    "reference_asset_ids": "asset_reference",
    "source_asset_ids": "asset_source",
    "recipe_ids": "recipe",
    "stage_item_ids": "stage_input",
    "job_ids": "job_input",
    "derived_image_ids": "derivative",
}


def _protected_reasons(refs: dict) -> list[str]:
    """从 count_references 结果派生 protected 原因摘要（非空分类才计入）。"""
    reasons: list[str] = []
    references = refs.get("references", {})
    for key, reason in _REASON_KEYS.items():
        if references.get(key):
            reasons.append(reason)
    if refs.get("active_job_ids"):
        reasons.append("active_job")
    return reasons


def preview(session: Session, storage: StorageManager,
            image_ids: list[str] | None = None) -> dict:
    """两阶段之一：只统计不删除。protected 图不计入预计释放字节。

    返回（向后兼容保留 candidate_count/total_bytes/protected_count）：
    - candidate_count：全部 REJECT 候选；
    - deletable_count：引用检查通过、实际可删的数量；
    - protected_count：被引用保护而跳过的数量；
    - total_bytes：仅 deletable 的预计释放字节；
    - protected_items：[{image_id, reasons:[...]}]，reasons 取自 count_references 的非空分类。
    """
    candidates = _candidates(session, image_ids)
    total_bytes = 0
    protected_items: list[dict] = []
    for image in candidates:
        refs = image_reference_service.count_references(session, image.id)
        reasons = _protected_reasons(refs)
        if reasons:
            protected_items.append({"image_id": image.id, "reasons": reasons})
            continue
        total_bytes += _image_disk_bytes(session, storage, image)
    return {
        "candidate_count": len(candidates),
        "deletable_count": len(candidates) - len(protected_items),
        "protected_count": len(protected_items),
        "total_bytes": total_bytes,
        "protected_items": protected_items,
    }


def _collect_existing_files(session: Session, storage: StorageManager, image: Image) -> list[Path]:
    """original + 全部 variants 中**真实存在**的文件（缺失文件按不存在计）。"""
    paths: list[Path] = []
    original = storage.absolutize(image.file_path)
    if original.is_file():
        paths.append(original)
    for variant in _list_variants(session, image.id):
        path = storage.absolutize(variant.path)
        if path.is_file():
            paths.append(path)
    return paths


def _purge_image_rows(session: Session, image_id: str) -> None:
    """按外键依赖顺序清指针 + 删 variants 行 + 删 Image 行（不 commit，由调用方控制事务）。

    image_variants→images 无 ORM 关系，不能依赖 unit-of-work 自动排序，
    否则 DELETE images 会撞外键约束。
    """
    session.execute(update(JobItem).where(JobItem.image_id == image_id).values(image_id=None))
    session.execute(
        update(JobStageItem).where(JobStageItem.output_image_id == image_id)
        .values(output_image_id=None)
    )
    session.execute(delete(ImageVariant).where(ImageVariant.image_id == image_id))
    session.execute(delete(Image).where(Image.id == image_id))


def _remove_empty_image_dir(directory: Path, image_id: str) -> None:
    """仅当目录名即本图 id 且已空时删除（绝不误删 originals 根或其它图目录）。"""
    try:
        if directory.name == image_id and not any(directory.iterdir()):
            directory.rmdir()
    except OSError:
        pass


def _move_back(storage: StorageManager, moved: list[tuple[Path, Path]]) -> None:
    """把隔离区文件原子移回原路径（逆序）；单个失败只记日志，留待 stale 清理。"""
    for src, dst in reversed(moved):
        try:
            storage.atomic_move_into(dst, src.parent, src.name)
        except OSError:
            logger.warning("删除回滚移动文件失败（留待 stale 清理）: %s -> %s",
                           dst, src, exc_info=True)


def _delete_one(session: Session, storage: StorageManager, image: Image, cleanup_id: str) -> int:
    """删除单张未受保护图的文件 + DB 记录（trash staging 事务安全），返回释放字节数。

    口径（P0-3）：
    - original 与所有 variant 文件都已不存在（历史异常）：引用检查已通过，直接安全删 DB
      行（记录为文件本已缺失），freed=0，避免"DB 指向已丢文件"长期残留；
    - 部分文件存在：先原子移入隔离区，再 DB 事务删行；文件移动失败→已移回、DB 不动；
      DB commit 失败→rollback 并把隔离区文件原子移回；成功后才 purge 隔离区。
    """
    existing = _collect_existing_files(session, storage, image)
    freed = sum(path.stat().st_size for path in existing)

    # 文件本就全部缺失 → 直接删 DB 行（freed=0），不留"DB 指向已丢文件"残留
    if not existing:
        _purge_image_rows(session, image.id)
        session.commit()
        return 0

    staging_dir = storage.resolve_under(
        "images/temp", "delete_staging", cleanup_id, image.id)
    staging_dir.mkdir(parents=True, exist_ok=True)

    # 1) 文件 → 隔离区（同卷原子）；任一失败 → 已移回，DB 完全不动
    moved: list[tuple[Path, Path]] = []
    try:
        for index, src in enumerate(existing):
            dst = storage.atomic_move_into(src, staging_dir, f"{index}_{src.name}")
            moved.append((src, dst))
    except OSError:
        _move_back(storage, moved)
        raise _DeleteAborted("文件移入删除隔离区失败")

    # 2) DB 事务删行；失败 → rollback 并把隔离区文件原子移回
    try:
        _purge_image_rows(session, image.id)
        session.commit()
    except Exception:
        session.rollback()
        _move_back(storage, moved)
        raise _DeleteAborted("数据库删除失败")

    # 3) commit 成功 → 物理清除隔离区（purge 失败只记日志，不影响一致性，留待 stale 清理）
    storage.safe_delete(staging_dir)
    for path in existing:
        _remove_empty_image_dir(path.parent, image.id)
    return freed


def execute(session: Session, storage: StorageManager,
            image_ids: list[str] | None = None) -> dict:
    """两阶段之二：真删未受保护的 REJECT 图。"""
    candidates = _candidates(session, image_ids)
    cleanup_id = uuid.uuid4().hex  # 每次 execute 一个唯一隔离区批次
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
            freed = _delete_one(session, storage, image, cleanup_id)
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
        # 本轮引用检查通过、尝试删除的数量（成功 deleted + 失败 failed）
        "deletable_count": len(candidates) - protected_count,
        "failed": failed,
    }


def cleanup_stale_staging(storage: StorageManager, *, now: float | None = None,
                          retention_seconds: float = STALE_STAGING_RETENTION_SECONDS) -> int:
    """删除早于 retention 的 delete_staging 残留目录（启动/维护调用），返回删除数量。

    隔离区正常在 DB commit 成功后立即 purge；残留只可能来自 purge 失败 / 进程中断，
    此时 DB 已成功删除（或已回滚并移回文件）。残留目录可按 mtime 过期安全清理。
    失败只记日志，绝不阻断启动。
    """
    base = storage.resolve_under("images/temp", "delete_staging")
    if not base.is_dir():
        return 0
    now = time.time() if now is None else now
    removed = 0
    for child in base.iterdir():
        try:
            if not child.is_dir():
                continue
            if now - child.stat().st_mtime >= retention_seconds:
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
        except OSError:
            logger.warning("清理 stale delete staging 失败: %s", child, exc_info=True)
    return removed
