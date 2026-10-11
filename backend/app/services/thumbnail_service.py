"""ThumbnailService（Phase 0.11：图片缩略图系统）。

设计（合同冻结 API #2）：
- 规格：最长边 512px、WebP、quality 80；仅下采样（原图更小不放大），保持宽高比；
- 缩略图落 DataRoot ``images/thumbnails/<image_id>/thumbnail.webp``，
  变体记录在 ``image_variants``（variant_type=thumbnail，每图唯一），**不污染 images 表**；
- 图库只加载 thumbnail，Lightbox 才加载 original；
- **按需生成**：GET /images/{id}/thumbnail 时若 variant/文件缺失才生成（轻量 resize，
  绝不阻塞整库）；另提供 ``backfill_missing_thumbnails`` 批量回填历史缺图，
  可被脚本/启动维护调用，但浏览不依赖回填完成。
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image as PILImage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.ids import IMAGE_VARIANT, new_id
from app.models import Image, ImageVariant
from app.storage.manager import StorageManager

THUMBNAIL_MAX_SIDE = 512
THUMBNAIL_FORMAT = "webp"
THUMBNAIL_QUALITY = 80
THUMBNAIL_DIR = "images/thumbnails"
THUMBNAIL_FILENAME = "thumbnail.webp"


def render_webp(data: bytes) -> tuple[bytes, int, int]:
    """把原图字节渲染为 512px WebP(q80) 缩略图字节，返回 (webp_bytes, width, height)。

    - 最长边 > 512 才等比下采样；否则保持原尺寸（不放大小图）；
    - 保留透明通道（WebP 原生支持 alpha）；
    - 原图损坏/无法解码 → ValidationError（绝不把 PIL OSError 泄漏成 500）。
    """
    try:
        with PILImage.open(io.BytesIO(data)) as im:
            im.load()
            if im.mode == "P":
                im = im.convert("RGBA")
            w, h = im.size
            longest = max(w, h)
            if longest > THUMBNAIL_MAX_SIDE:
                ratio = THUMBNAIL_MAX_SIDE / longest
                im = im.resize(
                    (max(1, round(w * ratio)), max(1, round(h * ratio))),
                    PILImage.LANCZOS,
                )
            buffer = io.BytesIO()
            im.save(buffer, format="WEBP", quality=THUMBNAIL_QUALITY)
            return buffer.getvalue(), im.width, im.height
    except ValidationError:
        raise
    except Exception as error:  # noqa: BLE001 —— 解码/编码失败统一为可报告的 400
        raise ValidationError("无法生成缩略图（原图损坏或格式不受支持）",
                             code="THUMBNAIL_FAILED") from error


def find_thumbnail_variant(session: Session, image_id: str) -> ImageVariant | None:
    return session.execute(
        select(ImageVariant).where(
            ImageVariant.image_id == image_id,
            ImageVariant.variant_type == "thumbnail",
        )
    ).scalars().first()


def _write_thumbnail_file(storage: StorageManager, image_id: str, webp: bytes) -> str:
    """把 WebP 字节写入 images/thumbnails/<image_id>/thumbnail.webp，返回相对路径。"""
    dest_dir = storage.resolve_under(THUMBNAIL_DIR, image_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / THUMBNAIL_FILENAME
    target.write_bytes(webp)
    return storage.relative_to_root(target)


def get_or_create_thumbnail(
    session: Session, storage: StorageManager, image: Image,
) -> tuple[Path, ImageVariant]:
    """返回 (缩略图绝对路径, ImageVariant)；缺失则按需生成并落库。

    - variant 存在且文件在 → 直接返回；
    - variant 存在但文件丢失（被清理过）→ 重新生成并更新该行；
    - 无 variant → 从 original 生成、新建 ImageVariant(thumbnail)；
    - original 文件缺失 → NotFoundError(IMAGE_FILE_MISSING)。
    """
    variant = find_thumbnail_variant(session, image.id)
    if variant is not None and storage.absolutize(variant.path).is_file():
        return storage.absolutize(variant.path), variant

    original = storage.absolutize(image.file_path)
    if not original.is_file():
        raise NotFoundError("原图文件缺失，无法生成缩略图", code="IMAGE_FILE_MISSING")

    webp, width, height = render_webp(original.read_bytes())
    relative = _write_thumbnail_file(storage, image.id, webp)

    if variant is None:
        variant = ImageVariant(
            id=new_id(IMAGE_VARIANT),
            image_id=image.id,
            variant_type="thumbnail",
            path=relative,
            width=width,
            height=height,
            format=THUMBNAIL_FORMAT,
        )
        session.add(variant)
    else:
        variant.path = relative
        variant.width = width
        variant.height = height
        variant.format = THUMBNAIL_FORMAT
    session.commit()
    session.refresh(variant)
    return storage.absolutize(variant.path), variant


def iter_images_missing_thumbnail(session: Session) -> list[str]:
    """返回所有还没有 thumbnail variant 的 image_id（回填候选）。"""
    subquery = select(ImageVariant.image_id).where(ImageVariant.variant_type == "thumbnail")
    return list(session.execute(
        select(Image.id).where(~Image.id.in_(subquery))
    ).scalars().all())


def backfill_missing_thumbnails(
    session: Session, storage: StorageManager, *, limit: int | None = None,
) -> int:
    """为历史缺缩略图的图批量生成（脚本/启动维护用）。

    单张失败（原图损坏/缺失）跳过且回滚该张，不阻断整批；返回成功生成的数量。
    浏览路径不依赖本函数完成。
    """
    pending = iter_images_missing_thumbnail(session)
    created = 0
    for image_id in pending:
        if limit is not None and created >= limit:
            break
        image = session.get(Image, image_id)
        if image is None:
            continue
        try:
            get_or_create_thumbnail(session, storage, image)
            created += 1
        except Exception:  # noqa: BLE001 —— 单张失败不阻断回填
            session.rollback()
            continue
    return created
