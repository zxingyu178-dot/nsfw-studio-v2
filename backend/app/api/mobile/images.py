"""Mobile Bridge 图片内容端点（Bearer）。

GET /mobile/images/{image_id}/thumbnail | preview | original

- 复用 ThumbnailService / StorageManager，**不重建缓存链**；
- thumbnail 512 WebP、preview 1536 WebP、original 仅放大/详情用；
- 加 ETag、``Cache-Control: private``、``X-Content-Type-Options: nosniff``。
"""
from __future__ import annotations

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.mobile.deps import get_current_device, get_session, get_storage
from app.core.errors import ConflictError, NotFoundError
from app.core.filetypes import mime_for_suffix
from app.models import Job
from app.models.mobile_review import MobileReviewDevice
from app.services import image_event_service, image_service, mobile_mutation_service, prompt_service, thumbnail_service
from app.storage.manager import StorageManager

router = APIRouter(prefix="/mobile/images", tags=["mobile-images"])

_PRIVATE_CACHE = "private, max-age=300"


class MobileReviewConflict(ConflictError):
    status_code = 409
    code = "REVIEW_CONFLICT"
    message = "图片已被其他设备修改，请刷新后重试"


class MobileImageReviewRequest(BaseModel):
    action: Literal["KEEP", "REJECT", "RESET"] | None = None
    favorite: bool | None = None
    expected_revision: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)


def _mobile_image_detail(session: Session, image) -> dict:
    provenance = image_service.get_provenance(session, image.id)
    revision = image_event_service.image_revision(image)
    prompt_snapshot = None
    negative_prompt = None
    source_prompt_id = None
    source_prompt_version_id = None
    prompt_name = None
    prompt_version_no = None
    job = session.get(Job, image.job_id) if image.job_id else None
    if job is not None:
        prompt_snapshot = job.positive_prompt_snapshot or ""
        negative_prompt = job.negative_prompt_snapshot or ""
        try:
            snapshot = json.loads(job.workbench_snapshot_json or "{}")
        except ValueError:
            snapshot = {}
        if isinstance(snapshot, dict):
            source_prompt_id = snapshot.get("source_prompt_id")
            source_prompt_version_id = snapshot.get("source_prompt_version_id")
    if source_prompt_id:
        try:
            prompt = prompt_service.get_prompt(session, str(source_prompt_id))
            prompt_name = prompt.name
            if source_prompt_version_id:
                version = prompt_service.get_version(
                    session, str(source_prompt_id), str(source_prompt_version_id)
                )
                prompt_version_no = version.version_no
        except Exception:  # noqa: BLE001 —— 溯源横幅尽力展示，不阻断图片详情
            prompt_name = prompt_name or None
    return {
        "image_id": image.id,
        "width": image.width,
        "height": image.height,
        "created_at": image.created_at,
        "updated_at": image.updated_at,
        "revision": revision,
        "status": image.status,
        "is_favorite": bool(image.favorite),
        "kind": image.kind,
        "source": image.source,
        "job_id": image.job_id,
        "seed": image.seed,
        "generation_module": provenance.get("module_id"),
        "generation_metadata": {
            "module_id": provenance.get("module_id"),
            "module_version": provenance.get("module_version"),
            "provider": provenance.get("provider"),
            "binding_version": provenance.get("binding_version"),
            "workflow_hash": provenance.get("workflow_hash"),
            "binding_hash": provenance.get("binding_hash"),
            "scale": provenance.get("scale"),
            "parent_image_id": provenance.get("parent_image_id"),
            "root_image_id": provenance.get("root_image_id"),
        },
        "prompt_snapshot": prompt_snapshot,
        "negative_prompt": negative_prompt,
        "source_prompt_id": source_prompt_id,
        "source_prompt_version_id": source_prompt_version_id,
        "prompt_name": prompt_name,
        "prompt_version_no": prompt_version_no,
        "thumbnail_url": f"/mobile/images/{image.id}/thumbnail",
        "preview_url": f"/mobile/images/{image.id}/preview",
        "original_url": f"/mobile/images/{image.id}/original",
    }


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


@router.get("/{image_id}", summary="图片详情（Bearer；无路径/配置泄漏）")
def get_image_detail(image_id: str,
                     session: Session = Depends(get_session),
                     _device: MobileReviewDevice = Depends(get_current_device)) -> dict:
    image = image_service.get_image(session, image_id)
    return _mobile_image_detail(session, image)


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


@router.post("/{image_id}/review", summary="单图片审核（幂等 + 乐观锁，Bearer）")
def review_image(
    image_id: str,
    body: MobileImageReviewRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    session: Session = Depends(get_session),
    device: MobileReviewDevice = Depends(get_current_device),
) -> dict:
    if body.action is None and body.favorite is None:
        from app.core.errors import ValidationError
        raise ValidationError("action 与 favorite 至少提供一个", code="REVIEW_MUTATION_EMPTY")

    operation = f"image_review:{image_id}"
    payload = {
        "image_id": image_id,
        "action": body.action,
        "favorite": body.favorite,
        "expected_revision": body.expected_revision,
        "note": body.note,
    }
    replay = mobile_mutation_service.find_receipt(
        session, device_id=device.id, operation=operation,
        idempotency_key=idempotency_key, payload=payload,
    )
    if replay is not None:
        return {**replay, "idempotent_replay": True}

    image = image_service.get_image(session, image_id)
    current_revision = image_event_service.image_revision(image)
    if current_revision != body.expected_revision:
        session.rollback()
        raise MobileReviewConflict(details={
            "image": _mobile_image_detail(session, image),
            "revision": current_revision,
        })

    action_status = {"KEEP": "KEEP", "REJECT": "REJECT", "RESET": "NEW"}.get(body.action or "")
    image_service.apply_review_fields(
        image, status=action_status, favorite=body.favorite, review_note=body.note,
    )
    image_event_service.record_review_change(
        session, image,
        review_changed=action_status is not None,
        favorite_changed=body.favorite is not None,
        metadata_changed=body.note is not None,
        note=image.review_note,
    )
    detail = _mobile_image_detail(session, image)
    response = {"image": detail, "revision": detail["revision"], "idempotent_replay": False}
    mobile_mutation_service.add_receipt(
        session, device_id=device.id, operation=operation,
        idempotency_key=idempotency_key, payload=payload, response=response,
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        replay = mobile_mutation_service.replay_or_none(
            session, device_id=device.id, operation=operation,
            idempotency_key=idempotency_key, payload=payload,
        )
        if replay is not None:
            return {**replay, "idempotent_replay": True}
        raise MobileReviewConflict("并发提交冲突，请重试")
    return response
