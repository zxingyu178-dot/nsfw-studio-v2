"""Images / Gallery API（Phase 2C，规范 §四十四、§四十七、§四十八）。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_storage
from app.core.errors import NotFoundError
from app.core.filetypes import mime_for_suffix
from app.schemas.image import (
    ImageFavoriteRequest,
    ImageListResponse,
    ImageResponse,
    ImageReviewRequest,
    ImageWorkbenchResponse,
    image_response,
)
from app.services import image_service
from app.storage.manager import StorageManager

router = APIRouter(prefix="/images", tags=["images"])


@router.get("", response_model=ImageListResponse, summary="图库列表（job/review/favorite/source/date 过滤）")
def list_images(
    job_id: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    favorite: bool | None = Query(default=None),
    source: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> ImageListResponse:
    items, total = image_service.list_images(
        session, job_id=job_id, review_status=review_status, favorite=favorite,
        source=source, kind=kind, date_from=date_from, date_to=date_to, limit=limit, offset=offset,
    )
    return ImageListResponse(
        items=[image_response(image) for image in items], total=total, limit=limit, offset=offset
    )


@router.get("/{image_id}", response_model=ImageResponse, summary="图片详情")
def get_image(image_id: str, session: Session = Depends(get_session)) -> ImageResponse:
    return image_response(image_service.get_image(session, image_id))


@router.get("/{image_id}/content", summary="图片文件流")
def get_image_content(image_id: str, session: Session = Depends(get_session),
                      storage: StorageManager = Depends(get_storage)) -> FileResponse:
    image = image_service.get_image(session, image_id)
    absolute = storage.absolutize(image.file_path)
    if not absolute.is_file():
        raise NotFoundError("图片文件缺失", code="IMAGE_FILE_MISSING")
    suffix = absolute.suffix.lower()
    return FileResponse(absolute, media_type=mime_for_suffix(suffix))


@router.patch("/{image_id}/review", response_model=ImageResponse, summary="审核状态（保留/淘汰/未审核）")
def review_image(image_id: str, body: ImageReviewRequest, session: Session = Depends(get_session)) -> ImageResponse:
    return image_response(image_service.set_review(session, image_id, body.review_status))


@router.patch("/{image_id}/favorite", response_model=ImageResponse, summary="收藏切换")
def favorite_image(image_id: str, body: ImageFavoriteRequest, session: Session = Depends(get_session)) -> ImageResponse:
    return image_response(image_service.set_favorite(session, image_id, body.favorite))


@router.get("/{image_id}/workbench", response_model=ImageWorkbenchResponse,
            summary="Image → 生成工作台（复用 Job 当时的 WorkbenchSnapshot，规范 §四十七）")
def image_to_workbench(image_id: str, session: Session = Depends(get_session)) -> ImageWorkbenchResponse:
    image = image_service.get_image(session, image_id)
    if image.job_id is None:
        raise NotFoundError("该图片不来自生成任务", code="IMAGE_HAS_NO_JOB")
    from app.services import job_service

    job = job_service.get_job(session, image.job_id)
    snapshot = json.loads(job.workbench_snapshot_json)
    # Seed 默认 random；"使用此图 Seed" 由前端把 seed 写入快照后提交
    return ImageWorkbenchResponse(image_id=image.id, seed=image.seed, snapshot=snapshot)


@router.get("/by-job/{job_id}/summary", summary="按 Job 统计（规范 §四十九）")
def job_summary(job_id: str, session: Session = Depends(get_session)) -> dict:
    return image_service.job_gallery_summary(session, job_id)
