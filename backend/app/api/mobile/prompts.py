"""审核桥受限提示词评分；不开放桌面提示词编辑或引擎控制。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Integer, func, select, text
from sqlalchemy.orm import Session

from app.api.mobile.deps import get_current_device, get_session
from app.core.errors import ValidationError
from app.models import Image, PromptEvaluation
from app.models.mobile_review import ImageReviewSessionItem, MobileReviewDevice
from app.schemas.prompt import EvaluationDimension, EvaluationScore, PromptEvaluationCreateRequest
from app.services import mobile_v2_service, prompt_image_service, prompt_scoring_service, prompt_service

router = APIRouter(prefix="/mobile/prompts", tags=["mobile-prompt-review"])


class EvaluationRequest(BaseModel):
    prompt_version_id: str | None = None
    overall_score: EvaluationScore
    dimensions: dict[EvaluationDimension, EvaluationScore] | None = None
    notes: str | None = Field(default=None, max_length=10000)
    client_request_id: str = Field(min_length=1, max_length=128)


def _evaluation(row: PromptEvaluation | None) -> dict | None:
    if row is None:
        return None
    return {"evaluation_id": row.id, "prompt_id": row.prompt_id,
        "prompt_version_id": row.prompt_version_id, "overall_score": row.overall_score,
        "created_at": row.created_at, "notes": row.notes}


@router.get("/evaluations/{request_id}", summary="查询本设备评分回执")
def receipt(request_id: str, db: Session = Depends(get_session),
            device: MobileReviewDevice = Depends(get_current_device)) -> dict:
    row = db.execute(text(
        "SELECT operation,result_json FROM mobile_write_receipts WHERE device_id=:device AND request_id=:request"
    ), {"device": device.id, "request": request_id}).mappings().first()
    found = row is not None and row["operation"].startswith("evaluation:")
    return {"found": found, "evaluation": json.loads(row["result_json"]) if found else None}


@router.post("/{prompt_id}/evaluations", summary="追加版本评分，原子幂等")
def evaluate(prompt_id: str, body: EvaluationRequest, db: Session = Depends(get_session),
             device: MobileReviewDevice = Depends(get_current_device)) -> dict:
    # 缺失/null可选字段规范化为同一载荷，维度不补默认分。
    payload = {"prompt_version_id": body.prompt_version_id, "overall_score": body.overall_score,
        "dimensions": body.dimensions or {}, "notes": body.notes or ""}
    def write():
        request = PromptEvaluationCreateRequest(overall_score=body.overall_score,
            prompt_version_id=body.prompt_version_id, dimension_scores=body.dimensions or {}, notes=body.notes or "")
        row = prompt_scoring_service.create_evaluation(db, prompt_id, request, commit=False)
        result = _evaluation(row)
        result.pop("notes")
        return {**result, "client_request_id": body.client_request_id}
    return mobile_v2_service.atomic_write(db, device.id, body.client_request_id,
        "evaluation:" + prompt_id, payload, write)


def _images_query(db: Session, prompt_id: str, version_id: str | None):
    prompt_service.get_prompt(db, prompt_id)
    if version_id is not None:
        prompt_service.get_version(db, prompt_id, version_id)
    links = prompt_image_service._prompt_image_links(prompt_id=prompt_id, version_id=version_id)
    return select(Image).where(Image.id.in_(select(links.c.image_id)))


@router.get("/{prompt_id}/review-summary", summary="按版本统计，不混用跨版本分数")
def summary(prompt_id: str, version_id: str | None = None,
            db: Session = Depends(get_session), _device: MobileReviewDevice = Depends(get_current_device)) -> dict:
    images_query = _images_query(db, prompt_id, version_id)
    rows = select(PromptEvaluation).where(PromptEvaluation.prompt_id == prompt_id)
    ordered = rows.order_by(PromptEvaluation.created_at.desc(), PromptEvaluation.id.desc())
    latest = db.scalar(ordered.limit(1))
    version_latest = db.scalar(ordered.where(PromptEvaluation.prompt_version_id == version_id).limit(1))
    count = db.scalar(select(func.count()).select_from(rows.where(PromptEvaluation.prompt_version_id == version_id).subquery()))
    ids = images_query.with_only_columns(Image.id).subquery()
    known_seen = select(ImageReviewSessionItem.image_id).where(ImageReviewSessionItem.seen.is_(True))
    # 仅持久审核证据算seen，不能把图片进入feed视为已审阅。
    mobile_seen = text("SELECT image_id FROM mobile_image_seen WHERE seen=1")
    seen_condition = Image.reviewed_at.is_not(None) | Image.id.in_(known_seen) | Image.id.in_(mobile_seen)
    total, seen, keep, reject = db.execute(select(
        func.count(), func.coalesce(func.sum(seen_condition.cast(Integer)), 0),
        func.coalesce(func.sum((Image.status == "KEEP").cast(Integer)), 0),
        func.coalesce(func.sum((Image.status == "REJECT").cast(Integer)), 0),
    ).select_from(Image).where(Image.id.in_(select(ids.c.id)))).one()
    new_samples = False
    if version_latest:
        new_samples = bool(db.scalar(select(func.count()).select_from(Image).where(
            Image.id.in_(select(ids.c.id)), Image.created_at > version_latest.created_at)))
    return {"prompt_id": prompt_id, "prompt_version_id": version_id,
        "link_state": "EXACT" if version_id else "UNRESOLVED",
        "evaluation_count": count, "version_latest": _evaluation(version_latest),
        "prompt_latest": _evaluation(latest), "images_total": total, "seen_count": seen,
        "keep_count": keep, "reject_count": reject, "has_new_samples": new_samples}


@router.get("/{prompt_id}/images", summary="提示词版本图片分页")
def images(prompt_id: str, version_id: str | None = None,
           cursor: str | None = Query(default=None, max_length=128),
           limit: int = Query(default=50, ge=1, le=100),
           db: Session = Depends(get_session), _device: MobileReviewDevice = Depends(get_current_device)) -> dict:
    query = _images_query(db, prompt_id, version_id)
    # 此列表无更新水位语义，游标仅服务于有界组内分页，绑定精确评分对象。
    import base64
    target = f"{prompt_id}:{version_id or ''}"
    offset = 0
    if cursor:
        try:
            token = json.loads(base64.urlsafe_b64decode(cursor).decode())
            if token["target"] != target or type(token["offset"]) is not int or token["offset"] < 0:
                raise ValueError()
            offset = token["offset"]
        except (ValueError, KeyError, TypeError):
            raise ValidationError("图片分页位置无效") from None
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Image.created_at, Image.id).offset(offset).limit(limit)).all()
    has_more = offset + len(rows) < total
    next_cursor = base64.urlsafe_b64encode(json.dumps({"target": target, "offset": offset + len(rows)}).encode()).decode() if has_more else None
    return {"items": [{"image_id": row.id, "thumbnail_url": f"/mobile/images/{row.id}/thumbnail",
        "status": row.status, "is_current": False} for row in rows], "total": total,
        "current_index": offset, "next_cursor": next_cursor, "has_more": has_more}
