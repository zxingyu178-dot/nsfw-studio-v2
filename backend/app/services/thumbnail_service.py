"""RenditionService（Phase 0.11：图片缩略图/预览 rendition 系统）。

设计（合同冻结 API #2 + Phase 0.11.1 加固）：
- 规格：
  - ``thumbnail``：最长边 512px、WebP、quality 80；落 ``images/thumbnails/<image_id>/thumbnail.webp``；
  - ``preview``：最长边 1536px（落在 1280~1600）、WebP、quality 85；落
    ``images/previews/<image_id>/preview.webp``；供 Review Mode / Lightbox 渐进加载。
- 两者都**仅下采样**（原图更小不放大）、保持宽高比、保留 alpha 通道；
- 变体记录在 ``image_variants``（variant_type=thumbnail/preview，**只表同一逻辑 Image 的
  展示/缓存 rendition**，绝不把 upscaled/processed 派生 Image 塞进 variants）；
- 图库只加载 thumbnail，Review/Lightbox 先用 preview，需要 100% 时才加载 original；
- **并发安全**（P1-4）：per-(image_id, variant_type) 进程内锁 + double-checked、
  临时文件 + ``os.replace`` 原子替换正式文件、INSERT 撞唯一索引后 re-read 已存在行；
- **主动生成**（P1-3）：新图入库后基于内存字节 best-effort 生成 thumbnail；
- **后台回填**（P1-3）：低并发补齐历史缺图，浏览路径不依赖回填完成。
"""
from __future__ import annotations

import io
import logging
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image as PILImage
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.ids import IMAGE_VARIANT, new_id
from app.models import Image, ImageVariant
from app.storage.manager import StorageManager

logger = logging.getLogger(__name__)

# ---- rendition 规格 -------------------------------------------------------


@dataclass(frozen=True)
class RenditionSpec:
    max_side: int
    quality: int
    directory: str
    filename: str
    variant_type: str


THUMBNAIL_MAX_SIDE = 512
THUMBNAIL_FORMAT = "webp"
THUMBNAIL_QUALITY = 80
THUMBNAIL_DIR = "images/thumbnails"
THUMBNAIL_FILENAME = "thumbnail.webp"

PREVIEW_MAX_SIDE = 1536  # 落在 1280~1600
PREVIEW_QUALITY = 85
PREVIEW_DIR = "images/previews"
PREVIEW_FILENAME = "preview.webp"

VARIANT_SPECS: dict[str, RenditionSpec] = {
    "thumbnail": RenditionSpec(
        max_side=THUMBNAIL_MAX_SIDE, quality=THUMBNAIL_QUALITY,
        directory=THUMBNAIL_DIR, filename=THUMBNAIL_FILENAME, variant_type="thumbnail",
    ),
    "preview": RenditionSpec(
        max_side=PREVIEW_MAX_SIDE, quality=PREVIEW_QUALITY,
        directory=PREVIEW_DIR, filename=PREVIEW_FILENAME, variant_type="preview",
    ),
}


def _spec(variant_type: str) -> RenditionSpec:
    spec = VARIANT_SPECS.get(variant_type)
    if spec is None:
        raise ValidationError(f"不支持的 rendition 类型: {variant_type}", code="VARIANT_TYPE_INVALID")
    return spec


# ---- 进程内 per-(image_id, variant_type) 锁（带守卫，完成后清理避免泄漏） ----

_LOCK_GUARD = threading.Lock()
_VARIANT_LOCKS: dict[tuple[str, str], threading.Lock] = {}


def _acquire_lock(image_id: str, variant_type: str) -> tuple[threading.Lock, tuple[str, str]]:
    key = (image_id, variant_type)
    with _LOCK_GUARD:
        lock = _VARIANT_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _VARIANT_LOCKS[key] = lock
    lock.acquire()
    return lock, key


def _release_lock(key: tuple[str, str], lock: threading.Lock) -> None:
    lock.release()
    # 清理锁字典条目：仅当当前条目仍是我们持有的这把锁时才移除。
    # 已在等待同一锁对象的线程仍持有引用、不受影响；新进来的线程会建新锁，
    # 但 double-checked 已保证命中即返回，正确性不依赖锁复用。
    with _LOCK_GUARD:
        if _VARIANT_LOCKS.get(key) is lock:
            _VARIANT_LOCKS.pop(key, None)


# ---- 渲染 -----------------------------------------------------------------


def render_webp(data: bytes, *, max_side: int = THUMBNAIL_MAX_SIDE,
                quality: int = THUMBNAIL_QUALITY) -> tuple[bytes, int, int]:
    """把原图字节渲染为 WebP 字节，返回 (webp_bytes, width, height)。

    - 最长边 > max_side 才等比下采样；否则保持原尺寸（不放大小图）；
    - 保留透明通道（WebP 原生支持 alpha）；P 模式先转 RGBA；
    - 原图损坏/无法解码 → ValidationError（绝不把 PIL OSError 泄漏成 500）。
    """
    try:
        with PILImage.open(io.BytesIO(data)) as im:
            im.load()
            if im.mode == "P":
                im = im.convert("RGBA")
            w, h = im.size
            longest = max(w, h)
            if longest > max_side:
                ratio = max_side / longest
                im = im.resize(
                    (max(1, round(w * ratio)), max(1, round(h * ratio))),
                    PILImage.LANCZOS,
                )
            buffer = io.BytesIO()
            im.save(buffer, format="WEBP", quality=quality)
            return buffer.getvalue(), im.width, im.height
    except ValidationError:
        raise
    except Exception as error:  # noqa: BLE001 —— 解码/编码失败统一为可报告的 400
        raise ValidationError("无法生成缩略图（原图损坏或格式不受支持）",
                             code="THUMBNAIL_FAILED") from error


def render_thumbnail_webp(data: bytes) -> tuple[bytes, int, int]:
    """兼容旧签名：512px WebP(q80)。"""
    return render_webp(data, max_side=THUMBNAIL_MAX_SIDE, quality=THUMBNAIL_QUALITY)


def render_preview_webp(data: bytes) -> tuple[bytes, int, int]:
    """preview：长边 1536 WebP(q85)，仅下采样、保留 alpha。"""
    return render_webp(data, max_side=PREVIEW_MAX_SIDE, quality=PREVIEW_QUALITY)


# ---- variant 查询 ---------------------------------------------------------


def find_variant(session: Session, image_id: str, variant_type: str) -> ImageVariant | None:
    return session.execute(
        select(ImageVariant).where(
            ImageVariant.image_id == image_id,
            ImageVariant.variant_type == variant_type,
        )
    ).scalars().first()


def find_thumbnail_variant(session: Session, image_id: str) -> ImageVariant | None:
    return find_variant(session, image_id, "thumbnail")


# ---- 原子写 ---------------------------------------------------------------


def _atomic_write_webp(storage: StorageManager, image_id: str, spec: RenditionSpec,
                       webp: bytes) -> str:
    """在目标目录写临时文件（同卷）后用 os.replace 原子替换正式文件，返回相对路径。

    临时文件在 finally 中清理，杜绝半写 WebP 残留。
    """
    dest_dir = storage.resolve_under(spec.directory, image_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    temp_path = dest_dir / f".tmp-{uuid.uuid4().hex}.webp"
    try:
        with temp_path.open("wb") as handle:
            handle.write(webp)
            handle.flush()
            try:
                import os
                os.fsync(handle.fileno())
            except OSError:
                pass
        storage.atomic_move_into(temp_path, dest_dir, spec.filename)
    finally:
        storage.safe_delete(temp_path)
    target = dest_dir / spec.filename
    return storage.relative_to_root(target)


# ---- 核心生产链（并发安全） -----------------------------------------------


def _produce_variant(
    session: Session, storage: StorageManager, image: Image,
    variant_type: str, data: bytes,
) -> tuple[Path, ImageVariant]:
    """渲染 + 原子写 + 落库（调用方须已持锁并完成 double-checked）。"""
    spec = _spec(variant_type)
    webp, width, height = render_webp(data, max_side=spec.max_side, quality=spec.quality)
    relative = _atomic_write_webp(storage, image.id, spec, webp)

    variant = find_variant(session, image.id, variant_type)
    if variant is None:
        variant = ImageVariant(
            id=new_id(IMAGE_VARIANT),
            image_id=image.id,
            variant_type=variant_type,
            path=relative,
            width=width,
            height=height,
            format=THUMBNAIL_FORMAT,
        )
        session.add(variant)
        try:
            session.commit()
        except IntegrityError:
            # 跨进程/跨请求竞争：另一事务已插入同图同 variant。回滚后 re-read。
            session.rollback()
            existing = find_variant(session, image.id, variant_type)
            if existing is not None and storage.absolutize(existing.path).is_file():
                return storage.absolutize(existing.path), existing
            raise
    else:
        # variant 行存在但文件丢失（被清理过）→ 更新该行指向新文件
        variant.path = relative
        variant.width = width
        variant.height = height
        variant.format = THUMBNAIL_FORMAT
        session.commit()
    session.refresh(variant)
    return storage.absolutize(variant.path), variant


def get_or_create_variant(
    session: Session, storage: StorageManager, image: Image, variant_type: str,
) -> tuple[Path, ImageVariant]:
    """并发安全地返回 (rendition 绝对路径, ImageVariant)；缺失则按需生成。

    - 进程内 per-(image_id, variant_type) 锁 + 获锁后二次检查（double-checked），
      命中已存在 variant 且文件在则直接返回；
    - 写文件临时化 + os.replace 原子替换，杜绝半写 WebP；
    - INSERT 撞唯一索引 → rollback 后 re-read 已存在 variant（不抛 500）；
    - variant 行存在但文件丢失 → 安全重建并更新该行；
    - original 缺失 → NotFoundError(IMAGE_FILE_MISSING)。
    """
    _spec(variant_type)  # 校验类型
    lock, key = _acquire_lock(image.id, variant_type)
    try:
        # double-checked：获锁后重新查询，避免重复渲染/重复写盘
        variant = find_variant(session, image.id, variant_type)
        if variant is not None and storage.absolutize(variant.path).is_file():
            return storage.absolutize(variant.path), variant

        original = storage.absolutize(image.file_path)
        if not original.is_file():
            raise NotFoundError("原图文件缺失，无法生成缩略图", code="IMAGE_FILE_MISSING")

        return _produce_variant(session, storage, image, variant_type, original.read_bytes())
    finally:
        _release_lock(key, lock)


def get_or_create_thumbnail(
    session: Session, storage: StorageManager, image: Image,
) -> tuple[Path, ImageVariant]:
    """返回 (缩略图绝对路径, ImageVariant)；缺失则按需生成并落库。"""
    return get_or_create_variant(session, storage, image, "thumbnail")


def get_or_create_preview(
    session: Session, storage: StorageManager, image: Image,
) -> tuple[Path, ImageVariant]:
    """返回 (preview 绝对路径, ImageVariant)；缺失则按需生成并落库。"""
    return get_or_create_variant(session, storage, image, "preview")


def produce_thumbnail_from_bytes(
    session: Session, storage: StorageManager, image: Image, data: bytes,
) -> None:
    """入库后主动生成 thumbnail：基于已在内存的输出字节，不重新读盘。

    image 为 brand-new 行（理论上无并发），但仍走同一把锁/原子写/collision re-read。
    失败由调用方（import_outputs_transaction）兜底为 warning，绝不向外抛错。
    """
    lock, key = _acquire_lock(image.id, "thumbnail")
    try:
        variant = find_variant(session, image.id, "thumbnail")
        if variant is not None and storage.absolutize(variant.path).is_file():
            return
        _produce_variant(session, storage, image, "thumbnail", data)
    finally:
        _release_lock(key, lock)


# ---- 回填候选 -------------------------------------------------------------


def iter_images_missing_variant(session: Session, variant_type: str = "thumbnail") -> list[str]:
    """返回还没有指定 variant 的全部 image_id（回填候选）。"""
    _spec(variant_type)
    subquery = select(ImageVariant.image_id).where(ImageVariant.variant_type == variant_type)
    return list(session.execute(
        select(Image.id).where(~Image.id.in_(subquery))
    ).scalars().all())


def iter_images_missing_thumbnail(session: Session) -> list[str]:
    """返回所有还没有 thumbnail variant 的 image_id（回填候选）。"""
    return iter_images_missing_variant(session, "thumbnail")


def backfill_missing_thumbnails(
    session: Session, storage: StorageManager, *, limit: int | None = None,
    kind: str = "thumbnail",
) -> int:
    """为历史缺 rendition 的图批量生成（脚本/启动维护用）。

    单张失败（原图损坏/缺失）跳过且回滚该张，不阻断整批；返回成功生成的数量。
    浏览路径不依赖本函数完成。
    """
    pending = iter_images_missing_variant(session, kind)
    created = 0
    for image_id in pending:
        if limit is not None and created >= limit:
            break
        image = session.get(Image, image_id)
        if image is None:
            continue
        try:
            get_or_create_variant(session, storage, image, kind)
            created += 1
        except Exception:  # noqa: BLE001 —— 单张失败不阻断回填
            session.rollback()
            continue
    return created
