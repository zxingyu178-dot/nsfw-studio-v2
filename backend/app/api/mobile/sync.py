"""W3.0 移动端增量同步：事件流 + 全量快照。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.mobile.deps import get_current_device, get_session
from app.core.timeutil import utc_now_iso
from app.models import Image
from app.models.mobile_review import MobileReviewDevice
from app.services import image_event_service

router = APIRouter(prefix="/mobile", tags=["mobile-sync"])


def _image_sync_item(image: Image, revision: int) -> dict:
    return {
        "image_id": image.id,
        "width": image.width,
        "height": image.height,
        "created_at": image.created_at,
        "updated_at": image.updated_at,
        "revision": str(revision),
        "status": image.status,
        "is_favorite": bool(image.favorite),
        "kind": image.kind,
        "source": image.source,
        "job_id": image.job_id,
        "seed": image.seed,
        "thumbnail_url": f"/mobile/images/{image.id}/thumbnail",
        "preview_url": f"/mobile/images/{image.id}/preview",
        "original_url": f"/mobile/images/{image.id}/original",
    }


@router.get("/events", summary="增量事件流（不透明游标，断点恢复）")
def events(
    cursor: str | None = Query(default=None, description="上一页 next_cursor；首次同步可省略"),
    limit: int = Query(default=image_event_service.DEFAULT_EVENT_LIMIT, ge=1,
                       le=image_event_service.MAX_EVENT_LIMIT),
    session: Session = Depends(get_session),
    _device: MobileReviewDevice = Depends(get_current_device),
) -> dict:
    return image_event_service.list_events(session, cursor=cursor, limit=limit)


@router.get("/sync/snapshot", summary="全量快照（首次配对 / 游标过期恢复）")
def snapshot(
    session: Session = Depends(get_session),
    _device: MobileReviewDevice = Depends(get_current_device),
) -> dict:
    """读取快照与水位必须在同一 DB 读事务中，确保快照与后续增量事件无空隙。"""
    watermark = image_event_service.newest_seq(session)
    images = list(session.scalars(
        select(Image).order_by(Image.created_at.asc(), Image.id.asc())
    ))
    revisions = image_event_service.latest_event_seqs(session, [image.id for image in images])
    return {
        "images": [_image_sync_item(image, revisions.get(image.id, 0)) for image in images],
        "image_count": len(images),
        # 恢复游标水位：客户端从该 cursor 之后拉取事件，不会漏掉快照期间的变更
        "cursor": image_event_service.encode_cursor(watermark),
        "server_time": utc_now_iso(),
    }
