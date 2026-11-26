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
import stat
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import case, delete, select, update
from sqlalchemy.orm import Session

from app.models import Image, ImageVariant, JobItem, JobStageItem
from app.models.mobile_review import ImageReviewSession, ImageReviewSessionItem, MobileImageSeen
from app.services import image_event_service
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


def _disk_bytes(storage: StorageManager, image: Image, paths: list[str]) -> int:
    """original + 指定 variants 相对路径的文件字节（缺失/stat 失败按 0 计）。

    不触碰 Session：预览时用线程池并发 stat，冷缓存下把统计耗时从秒级压到百毫秒级。
    单次 stat 同时用于存在性判断（原先 is_file()+stat() 是两次系统调用）。
    """
    total = 0
    for relative in (image.file_path, *paths):
        try:
            info = storage.absolutize(relative).stat()
        except OSError:
            continue
        if stat.S_ISREG(info.st_mode):
            total += info.st_size
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
    if not candidates:
        return {
            "candidate_count": 0, "deletable_count": 0, "protected_count": 0,
            "total_bytes": 0, "protected_items": [], "deletable_ids": [],
        }
    started = time.perf_counter()
    # v0.37.1：批量引用检查。原实现逐张 5 次查询，487 张 REJECT 预览需数分钟，
    # 前端「删除淘汰图」长时间停在“准备中…”，实际被误判为删不掉。
    candidate_ids = [image.id for image in candidates]
    references = image_reference_service.count_references_many(session, candidate_ids)
    variants: dict[str, list[str]] = {image_id: [] for image_id in candidate_ids}
    for image_id, path in session.execute(
        select(ImageVariant.image_id, ImageVariant.path)
        .where(ImageVariant.image_id.in_(candidate_ids))
    ).all():
        variants.setdefault(image_id, []).append(path)
    protected_items: list[dict] = []
    deletable_images: list[Image] = []
    for image in candidates:
        refs = references.get(image.id) or {"references": {}, "active_job_ids": []}
        reasons = _protected_reasons(refs)
        if reasons:
            protected_items.append({"image_id": image.id, "reasons": reasons})
        else:
            deletable_images.append(image)
    # 并发 stat：HDD/Defender 冷缓存下逐张串行 stat 可达数秒，是"点击无反应"的主要来源
    total_bytes = 0
    if deletable_images:
        with ThreadPoolExecutor(max_workers=min(8, len(deletable_images))) as pool:
            total_bytes = sum(pool.map(
                lambda image: _disk_bytes(storage, image, variants.get(image.id, [])),
                deletable_images,
            ))
    logger.info(
        "废片清理预览：候选 %s，可删 %s，受保护 %s，合计 %.1f MB，用时 %.0f ms",
        len(candidates), len(deletable_images), len(protected_items),
        total_bytes / 1048576, (time.perf_counter() - started) * 1000,
    )
    return {
        "candidate_count": len(candidates),
        "deletable_count": len(candidates) - len(protected_items),
        "protected_count": len(protected_items),
        "total_bytes": total_bytes,
        "protected_items": protected_items,
        "deletable_ids": [image.id for image in deletable_images],
    }


def _existing_files(storage: StorageManager, image: Image,
                    variant_paths: list[str]) -> list[tuple[Path, int]]:
    """original + 指定 variants 中真实存在的文件及字节数（缺失按不存在计）。"""
    found: list[tuple[Path, int]] = []
    for relative in (image.file_path, *variant_paths):
        try:
            path = storage.absolutize(relative)
            info = path.stat()
        except OSError:
            continue
        if stat.S_ISREG(info.st_mode):
            found.append((path, info.st_size))
    return found


def _purge_image_rows(session: Session, image_id: str) -> None:
    """按外键依赖顺序清指针 + 删 variants 行 + 删 Image 行（不 commit，由调用方控制事务）。

    image_variants→images 无 ORM 关系，不能依赖 unit-of-work 自动排序，
    否则 DELETE images 会撞外键约束。
    W3.0：IMAGE_REMOVED 事件在 DELETE 之前写入同一事务；事件无 images 外键，删除后仍可读。
    """
    image = session.get(Image, image_id)
    if image is not None:
        image_event_service.record_image_removed(session, image)
    session.execute(update(JobItem).where(JobItem.image_id == image_id).values(image_id=None))
    session.execute(
        update(JobStageItem).where(JobStageItem.output_image_id == image_id)
        .values(output_image_id=None)
    )
    # 手机审核队列 / 设备已读标记也引用 images.id（前者 NO ACTION 会阻断删除）：
    # 图片既然已确认永久删除，这些引用必须同步清掉，否则 DELETE images 触发外键约束失败。
    # 图片被永久删除 → 同步扣减所在审核会话的 total_count，避免会话进度分母虚高
    affected_sessions = select(ImageReviewSessionItem.session_id).where(
        ImageReviewSessionItem.image_id == image_id
    )
    session.execute(
        update(ImageReviewSession)
        .where(ImageReviewSession.id.in_(affected_sessions))
        .values(total_count=case(
            (ImageReviewSession.total_count > 0, ImageReviewSession.total_count - 1),
            else_=0,
        ))
    )
    session.execute(
        delete(ImageReviewSessionItem).where(ImageReviewSessionItem.image_id == image_id)
    )
    session.execute(delete(MobileImageSeen).where(MobileImageSeen.image_id == image_id))
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


def _delete_one(session: Session, storage: StorageManager, image: Image,
                existing: list[tuple[Path, int]], staging_dir: Path) -> int:
    """删除单张未受保护图的文件 + DB 记录（trash staging 事务安全），返回释放字节数。

    口径（P0-3）：
    - original 与所有 variant 文件都已不存在（历史异常）：引用检查已通过，直接安全删 DB
      行（记录为文件本已缺失），freed=0，避免"DB 指向已丢文件"长期残留；
    - 部分文件存在：先原子移入隔离区，再 DB 事务删行；文件移动失败→已移回、DB 不动；
      DB commit 失败→rollback 并把隔离区文件原子移回；隔离区由 execute 在整批结束后统一清除。
    """
    freed = sum(size for _, size in existing)

    # 文件本就全部缺失 → 直接删 DB 行（freed=0），不留"DB 指向已丢文件"残留
    if not existing:
        _purge_image_rows(session, image.id)
        session.commit()
        return 0

    staging_dir.mkdir(parents=True, exist_ok=True)

    # 1) 文件 → 隔离区（同卷原子）；任一失败 → 已移回，DB 完全不动
    moved: list[tuple[Path, Path]] = []
    try:
        for index, (src, _) in enumerate(existing):
            dst = storage.atomic_move_into(src, staging_dir, f"{index}_{src.name}")
            moved.append((src, dst))
    except OSError as error:
        logger.warning("图片 %s 移入删除隔离区失败: %r", image.id, error, exc_info=True)
        _move_back(storage, moved)
        raise _DeleteAborted("文件移入删除隔离区失败")

    # 2) DB 事务删行；失败 → rollback 并把隔离区文件原子移回
    try:
        _purge_image_rows(session, image.id)
        session.commit()
    except Exception as error:
        session.rollback()
        _move_back(storage, moved)
        logger.warning("删除图片 %s 的数据库记录失败: %r", image.id, error, exc_info=True)
        raise _DeleteAborted(f"数据库删除失败（{type(error).__name__}）")

    for path, _ in existing:
        _remove_empty_image_dir(path.parent, image.id)
    return freed


def execute(session: Session, storage: StorageManager,
            image_ids: list[str] | None = None) -> dict:
    """两阶段之二：真删未受保护的 REJECT 图。

    v0.37.3 性能优化（原实现 59 张需数分钟）：
    - variants 一次 IN 查询取回（原实现逐图一次 SQL）；
    - 隔离区每批只建一次根目录，逐图子目录，成功批次合并清理；
    - ``absolutize`` 走纯词法归一化、stat 单次调用（原实现每文件 Path.resolve()+2 次系统调用）。
    仍保留逐图 commit：单张失败只回滚该张、不阻断其余（事务安全语义不变）。
    """
    started = time.perf_counter()
    candidates = _candidates(session, image_ids)
    if not candidates:
        return {"deleted_count": 0, "deleted_bytes": 0, "protected_count": 0,
                "deletable_count": 0, "failed": []}
    candidate_ids = [image.id for image in candidates]
    references = image_reference_service.count_references_many(session, candidate_ids)
    variants: dict[str, list[str]] = {image_id: [] for image_id in candidate_ids}
    for image_id, path in session.execute(
        select(ImageVariant.image_id, ImageVariant.path)
        .where(ImageVariant.image_id.in_(candidate_ids))
    ).all():
        variants.setdefault(image_id, []).append(path)

    cleanup_id = uuid.uuid4().hex  # 每次 execute 一个唯一隔离区批次
    staging_root = storage.resolve_under("images/temp", "delete_staging", cleanup_id)
    deleted_count = 0
    deleted_bytes = 0
    protected_count = 0
    failed: list[dict] = []
    committed: list[Path] = []
    for image in candidates:
        refs = references.get(image.id) or {"references": {}, "active_job_ids": []}
        if refs["total"] > 0 or refs["active_job_ids"]:
            protected_count += 1
            continue
        staging_dir = staging_root / image.id
        try:
            existing = _existing_files(storage, image, variants.get(image.id, []))
            freed = _delete_one(session, storage, image, existing, staging_dir)
        except Exception as error:  # noqa: BLE001 —— 单张失败不阻断其余
            session.rollback()
            failed.append({
                "image_id": image.id,
                "error_code": getattr(error, "code", "DELETE_FAILED"),
                "message": str(error),
            })
            continue
        deleted_count += 1
        deleted_bytes += freed
        committed.append(staging_dir)
    # 只清理 DB 已提交的成功批次；失败批次残留留给 stale 清理（移回失败时绝不丢文件）
    for directory in committed:
        storage.safe_delete(directory)
    if committed:
        try:
            staging_root.rmdir()
        except OSError:
            pass
    logger.info(
        "废片清理执行：候选 %s，已删 %s，受保护 %s，失败 %s，释放 %.1f MB，用时 %.0f ms",
        len(candidates), deleted_count, protected_count, len(failed),
        deleted_bytes / 1048576, (time.perf_counter() - started) * 1000,
    )
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
