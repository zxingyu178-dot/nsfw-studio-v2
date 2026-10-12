"""冻结式 ImageReviewSessionService（桌面 / 手机共用，Phase 0.13 核心）。

语义（合同冻结）：
- **冻结队列**：创建 session 时把符合 filter（默认 ``status=NEW, created_desc``）的
  image_id 顺序写进 ``mobile_review_session_items``；之后这些图 NEW→KEEP/REJECT
  **不改变队列顺序与成员**（绝对 item_index，不压缩）。
- **单事务**：一次 decision 同事务更新 Image.status/favorite + SessionItem.seen +
  session 的 seen_count/progress，失败全部 rollback。
- **并发冲突**：decision 带 ``expected_status`` / ``expected_updated_at``，
  状态已被他处修改 → 409 REVIEW_CONFLICT 并返回当前权威 Image。
- **不允许永久删除**：Bridge 只做 KEEP/REJECT/favorite/RESET，绝不碰 cleanup。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ConflictError, NotFoundError, ValidationError
from app.core.ids import MOBILE_REVIEW_SESSION, MOBILE_REVIEW_SESSION_ITEM, new_id
from app.core.timeutil import utc_now_iso
from app.models import Image
from app.models.mobile_review import ImageReviewSession, ImageReviewSessionItem

# decision action 取值（审核状态动作；favorite 由独立 bool 字段控制）
DECISION_ACTIONS = ("KEEP", "REJECT", "RESET")
DEFAULT_FILTER = {"status": "NEW", "sort": "created_desc"}


class ReviewSessionNotFound(NotFoundError):
    code = "REVIEW_SESSION_NOT_FOUND"


class ReviewItemNotFound(NotFoundError):
    code = "REVIEW_ITEM_NOT_FOUND"


class ImageNotFound(NotFoundError):
    code = "IMAGE_NOT_FOUND"


class ReviewConflict(ConflictError):
    status_code = 409
    code = "REVIEW_CONFLICT"
    message = "图片状态已被他处修改"


class ReviewSessionNotComplete(AppError):
    status_code = 409
    code = "REVIEW_SESSION_NOT_COMPLETE"
    message = "仍有未审核条目"


# ---- filter 解析（默认 status=NEW, created_desc；与图库列表排序口径一致） ----


def _resolve_filter(filter_obj: dict[str, Any] | None) -> dict[str, Any]:
    f = dict(DEFAULT_FILTER)
    if filter_obj:
        f.update({k: v for k, v in filter_obj.items() if v is not None})
    if f.get("status") is None:
        f["status"] = "NEW"
    if f.get("sort") is None:
        f["sort"] = "created_desc"
    return f


def _freeze_query(f: dict[str, Any]):
    query = select(Image.id)
    status = f.get("status")
    if status is not None:
        query = query.where(Image.status == status)
    job_id = f.get("job_id")
    if job_id is not None:
        # Gallery「按任务审核」：冻结某 job 产出图的稳定队列（口径对齐 image list）
        query = query.where(Image.job_id == job_id)
    sort = f.get("sort", "created_desc")
    if sort == "created_asc":
        order_by = (Image.created_at.asc(), Image.id.asc())
    else:
        order_by = (Image.created_at.desc(), Image.id.desc())
    return query.order_by(*order_by)


# ---- DTO ----


@dataclass(frozen=True)
class SessionSummary:
    id: str
    status: str
    total_count: int
    seen_count: int
    current_index: int
    created_at: str
    updated_at: str
    filter: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "total_count": self.total_count,
            "seen_count": self.seen_count,
            "current_index": self.current_index,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "filter": self.filter,
        }


def _summary(row: ImageReviewSession) -> SessionSummary:
    return SessionSummary(
        id=row.id, status=row.status, total_count=row.total_count,
        seen_count=row.seen_count, current_index=row.current_index,
        created_at=row.created_at, updated_at=row.updated_at,
        filter=json.loads(row.filter_json or "{}"),
    )


# ---- CRUD ----


def create_session(session: Session, filter_obj: dict[str, Any] | None = None) -> SessionSummary:
    f = _resolve_filter(filter_obj)
    image_ids: list[str] = list(session.execute(_freeze_query(f)).scalars().all())

    row = ImageReviewSession(
        id=new_id(MOBILE_REVIEW_SESSION),
        filter_json=json.dumps(f, ensure_ascii=False),
        total_count=len(image_ids),
        seen_count=0,
        status="ACTIVE",
        current_index=0,
    )
    session.add(row)
    for index, image_id in enumerate(image_ids):
        session.add(ImageReviewSessionItem(
            id=new_id(MOBILE_REVIEW_SESSION_ITEM),
            session_id=row.id,
            item_index=index,
            image_id=image_id,
            seen=False,
        ))
    session.commit()
    session.refresh(row)
    return _summary(row)


def get_latest_session(session: Session) -> SessionSummary | None:
    """恢复不重建：返回最近一个 ACTIVE 会话；无 ACTIVE 则返回最近创建的会话（可能 COMPLETED）。"""
    row = session.execute(
        select(ImageReviewSession)
        .order_by(ImageReviewSession.created_at.desc(), ImageReviewSession.id.desc())
        .limit(1)
    ).scalars().first()
    if row is None:
        return None
    return _summary(row)


def _must_get_session(session: Session, session_id: str) -> ImageReviewSession:
    row = session.get(ImageReviewSession, session_id)
    if row is None:
        raise ReviewSessionNotFound()
    return row


def queue_page(
    session: Session, session_id: str, *, page: int = 1, page_size: int = 50,
) -> dict[str, Any]:
    """返回队列一页；index 为冻结的绝对 index，不压缩。"""
    if page < 1:
        raise ValidationError("page 必须 >= 1", code="PAGE_INVALID")
    if page_size < 1 or page_size > 200:
        raise ValidationError("page_size 取值范围为 1-200", code="PAGE_SIZE_INVALID")
    row = _must_get_session(session, session_id)

    total = row.total_count
    offset = (page - 1) * page_size
    items = list(session.execute(
        select(ImageReviewSessionItem, Image)
        .join(Image, Image.id == ImageReviewSessionItem.image_id)
        .where(ImageReviewSessionItem.session_id == session_id)
        .order_by(ImageReviewSessionItem.item_index.asc())
        .limit(page_size).offset(offset)
    ).all())

    return {
        "items": [
            {
                "index": item.item_index,
                "seen": item.seen,
                "image": _image_summary(image),
            }
            for item, image in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _image_summary(image: Image) -> dict[str, Any]:
    """MobileImageSummary DTO：不下发 DataRoot/绝对路径/DB 路径/workflow 路径。"""
    iid = image.id
    return {
        "image_id": iid,
        "width": image.width,
        "height": image.height,
        "created_at": image.created_at,
        "updated_at": image.updated_at,
        "status": image.status,
        "is_favorite": bool(image.favorite),
        "kind": image.kind,
        "job_id": image.job_id,
        "seed": image.seed,
        "thumbnail_url": f"/mobile/images/{iid}/thumbnail",
        "preview_url": f"/mobile/images/{iid}/preview",
        "original_url": f"/mobile/images/{iid}/original",
    }


# ---- decision ----


def apply_decision(
    session: Session,
    session_id: str,
    *,
    item_index: int | None = None,
    image_id: str | None = None,
    action: str | None = None,
    favorite: bool | None = None,
    expected_status: str | None = None,
    expected_updated_at: str | None = None,
) -> dict[str, Any]:
    """同事务应用一次审核决策；失败全 rollback。

    - action: KEEP→KEEP / REJECT→REJECT / RESET→NEW；
    - favorite: true→is_favorite=true（审核状态独立）/ false→取消收藏；
    - expected_status / expected_updated_at: 乐观锁，不一致 → 409 REVIEW_CONFLICT。
    """
    if action is not None and action not in DECISION_ACTIONS:
        raise ValidationError(f"非法 action: {action}", code="DECISION_ACTION_INVALID")

    row = _must_get_session(session, session_id)

    item: ImageReviewSessionItem | None = None
    if item_index is not None:
        item = session.execute(
            select(ImageReviewSessionItem).where(
                ImageReviewSessionItem.session_id == session_id,
                ImageReviewSessionItem.item_index == item_index,
            )
        ).scalars().first()
    elif image_id is not None:
        item = session.execute(
            select(ImageReviewSessionItem).where(
                ImageReviewSessionItem.session_id == session_id,
                ImageReviewSessionItem.image_id == image_id,
            )
        ).scalars().first()
    if item is None:
        raise ReviewItemNotFound()

    image = session.get(Image, item.image_id)
    if image is None:
        raise ImageNotFound()

    # 乐观锁：调用方若传了期望值，则与当前权威状态比对
    if expected_status is not None and image.status != expected_status:
        session.rollback()
        raise ReviewConflict(details={  # type: ignore[call-arg]
            "image": _image_summary(image),
            "current_status": image.status,
            "current_updated_at": image.updated_at,
        })
    if expected_updated_at is not None and image.updated_at != expected_updated_at:
        session.rollback()
        raise ReviewConflict(details={  # type: ignore[call-arg]
            "image": _image_summary(image),
            "current_status": image.status,
            "current_updated_at": image.updated_at,
        })

    now = utc_now_iso()
    # 1) 审核状态动作
    if action == "KEEP":
        image.status = "KEEP"
        image.review_status = "KEPT"
        image.reviewed_at = now
        item.seen = True
    elif action == "REJECT":
        image.status = "REJECT"
        image.review_status = "REJECTED"
        image.reviewed_at = now
        item.seen = True
    elif action == "RESET":
        image.status = "NEW"
        image.review_status = "UNREVIEWED"
        image.reviewed_at = None
        item.seen = False

    # 2) 收藏（独立于审核状态；收藏即代表已看过该图）
    if favorite is not None:
        image.favorite = bool(favorite)
        item.seen = True

    # 3) 重算会话 seen_count（基于 items 的 seen 标志）
    seen_count = int(session.execute(
        select(func.count()).select_from(ImageReviewSessionItem)
        .where(ImageReviewSessionItem.session_id == session_id,
               ImageReviewSessionItem.seen.is_(True))
    ).scalar_one())
    row.seen_count = seen_count
    row.updated_at = now

    session.commit()
    session.refresh(image)
    session.refresh(row)
    return {
        "session": _summary(row).to_dict(),
        "item_index": item.item_index,
        "image": _image_summary(image),
    }


def update_position(session: Session, session_id: str, item_index: int) -> SessionSummary:
    """记录当前浏览位置（断点续看），不改变 seen。"""
    row = _must_get_session(session, session_id)
    if item_index < 0 or item_index >= row.total_count:
        raise ValidationError("item_index 越界", code="POSITION_OUT_OF_RANGE")
    row.current_index = item_index
    row.updated_at = utc_now_iso()
    session.commit()
    session.refresh(row)
    return _summary(row)


def complete_session(session: Session, session_id: str) -> dict[str, Any]:
    """标记会话完成；仍有 seen=false 则不强完成，返回 remaining_count。"""
    row = _must_get_session(session, session_id)
    remaining = int(session.execute(
        select(func.count()).select_from(ImageReviewSessionItem)
        .where(ImageReviewSessionItem.session_id == session_id,
               ImageReviewSessionItem.seen.is_(False))
    ).scalar_one())
    summary = _summary(row).to_dict()
    if remaining > 0:
        return {**summary, "completed": False, "remaining_count": remaining}
    row.status = "COMPLETED"
    row.updated_at = utc_now_iso()
    session.commit()
    session.refresh(row)
    return {**_summary(row).to_dict(), "completed": True, "remaining_count": 0}
