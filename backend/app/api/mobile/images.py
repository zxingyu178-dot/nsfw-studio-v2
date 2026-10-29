"""Mobile Bridge 图片内容端点（Bearer）。

GET /mobile/images/{image_id}/thumbnail | preview | original

- 复用 ThumbnailService / StorageManager，**不重建缓存链**；
- thumbnail 512 WebP、preview 1536 WebP、original 仅放大/详情用；
- 加 ETag、``Cache-Control: private``、``X-Content-Type-Options: nosniff``。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.mobile.deps import get_current_device, get_session, get_storage
from app.core.errors import NotFoundError
from app.core.filetypes import mime_for_suffix
from app.models.mobile_review import MobileReviewDevice
from app.services import image_service, thumbnail_service
from app.storage.manager import StorageManager

router = APIRouter(prefix="/mobile/images", tags=["mobile-images"])

_PRIVATE_CACHE = "private, max-age=300"


@router.get("/feed", summary="有序图片增量（Bearer）")
def feed(cursor: str | None = Query(default=None, max_length=512),
         limit: int = Query(default=50, ge=1, le=100),
         session: Session = Depends(get_session),
         _device: MobileReviewDevice = Depends(get_current_device)) -> dict:
    from app.services import mobile_v2_service
    return mobile_v2_service.feed(session, cursor, limit)


@router.get("/{image_id}/details", summary="生成快照详情（Bearer）")
def details(image_id: str, session: Session = Depends(get_session),
            _device: MobileReviewDevice = Depends(get_current_device)) -> dict:
    from app.services import mobile_v2_service
    return mobile_v2_service.image_details(session, image_service.get_image(session, image_id))


def _file_response(absolute, *, etag: str, media_type: str) -> FileResponse:
    return FileResponse(
        absolute,
        media_type=media_type,
        headers={
            "ETag": etag,
            "Cache-Control": _PRIVATE_CACHE,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{image_id}/thumbnail", summary="缩略图 512 WebP（Bearer）")
def get_thumbnail(image_id: str,
                 session: Session = Depends(get_session),
                 storage: StorageManager = Depends(get_storage),
                 _device: MobileReviewDevice = Depends(get_current_device)) -> FileResponse:
    image = image_service.get_image(session, image_id)
    absolute, variant = thumbnail_service.get_or_create_thumbnail(session, storage, image)
    return _file_response(
        absolute,
        etag=f'"thumb-{image.id}-{variant.width}x{variant.height}-{image.updated_at}"',
        media_type="image/webp",
    )


@router.get("/{image_id}/preview", summary="预览 1536 WebP（Bearer；默认档位）")
def get_preview(image_id: str,
               session: Session = Depends(get_session),
               storage: StorageManager = Depends(get_storage),
               _device: MobileReviewDevice = Depends(get_current_device)) -> FileResponse:
    image = image_service.get_image(session, image_id)
    absolute, variant = thumbnail_service.get_or_create_preview(session, storage, image)
    return _file_response(
        absolute,
        etag=f'"preview-{image.id}-{variant.width}x{variant.height}-{image.updated_at}"',
        media_type="image/webp",
    )


@router.get("/{image_id}/original", summary="原图（Bearer；仅放大/详情，谨慎）")
def get_original(image_id: str,
                session: Session = Depends(get_session),
                storage: StorageManager = Depends(get_storage),
                _device: MobileReviewDevice = Depends(get_current_device)) -> FileResponse:
    image = image_service.get_image(session, image_id)
    absolute = storage.absolutize(image.file_path)
    if not absolute.is_file():
        raise NotFoundError("原图文件缺失", code="IMAGE_FILE_MISSING")
    return _file_response(
        absolute,
        etag=f'"orig-{image.id}-{image.width}x{image.height}-{image.updated_at}"',
        media_type=mime_for_suffix(absolute.suffix.lower()),
    )
