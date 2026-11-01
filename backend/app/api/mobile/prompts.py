"""Mobile Prompt 审核：版本/整体评分、汇总、图片分页与回执（Bearer）。

- V2 客户端合同：``/{prompt_id}/evaluations`` + ``/evaluations/{client_request_id}``；
- 旧 W3 版本评分端点保留兼容，但 operation 使用稳定短标识；
- 评分复用 PromptEvaluation，source=mobile，不改 Prompt 状态。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.mobile.deps import get_current_device, get_session
from app.models import PromptEvaluation
from app.models.mobile_review import MobileReviewDevice
from app.schemas.prompt import EvaluationDimension, EvaluationScore, PromptEvaluationCreateRequest
from app.services import mobile_mutation_service, mobile_v2_service, prompt_scoring_service, prompt_service

router = APIRouter(prefix="/mobile/prompts", tags=["mobile-prompts"])

OP_PROMPT_EVALUATION_W3 = "prompt_evaluation_w3"


class MobilePromptEvaluationRequest(BaseModel):
    overall_score: EvaluationScore
    dimension_scores: dict[EvaluationDimension, EvaluationScore] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=2000)


class MobilePromptEvaluationV2Request(BaseModel):
    """V2 客户端冻结契约：version 可空表示“对提示词整体评分”。"""

    prompt_version_id: str | None = Field(default=None, max_length=64)
    overall_score: EvaluationScore
    dimensions: dict[EvaluationDimension, EvaluationScore] | None = None
    notes: str = Field(default="", max_length=10000)
    client_request_id: str = Field(min_length=1, max_length=128)


def _evaluation_dto(evaluation: PromptEvaluation) -> dict:
    import json

    return {
        "id": evaluation.id,
        "prompt_id": evaluation.prompt_id,
        "prompt_version_id": evaluation.prompt_version_id,
        "overall_score": evaluation.overall_score,
        "dimension_scores": json.loads(evaluation.dimension_scores_json or "{}"),
        "source": evaluation.source,
        "notes": evaluation.notes,
        "created_at": evaluation.created_at,
    }


@router.post(
    "/{prompt_id}/versions/{version_id}/evaluation",
    summary="W3 Prompt 版本评分（幂等，source=mobile；不改 Prompt 状态）",
    status_code=201,
)
def create_evaluation(
    prompt_id: str,
    version_id: str,
    body: MobilePromptEvaluationRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    session: Session = Depends(get_session),
    device: MobileReviewDevice = Depends(get_current_device),
) -> dict:
    prompt_service.get_version(session, prompt_id, version_id)  # 校验版本确实属于该 Prompt
    operation = OP_PROMPT_EVALUATION_W3
    payload = {
        "prompt_id": prompt_id,
        "version_id": version_id,
        "overall_score": body.overall_score,
        "dimension_scores": body.dimension_scores,
        "notes": body.notes,
    }
    replay = mobile_mutation_service.find_receipt(
        session, device_id=device.id, operation=operation,
        idempotency_key=idempotency_key, payload=payload,
    )
    if replay is not None:
        return {**replay, "idempotent_replay": True}

    request = PromptEvaluationCreateRequest(
        overall_score=body.overall_score,
        dimension_scores=body.dimension_scores,
        notes=body.notes,
        prompt_version_id=version_id,
    )
    evaluation = prompt_scoring_service.create_evaluation(
        session, prompt_id, request, source="mobile", commit=False,
    )
    response = {"evaluation": _evaluation_dto(evaluation), "idempotent_replay": False}
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
        raise
    return response


@router.get(
    "/{prompt_id}/versions/{version_id}/evaluations",
    summary="查询指定 Prompt Version 的评分记录（W3 兼容）",
)
def list_evaluations(
    prompt_id: str,
    version_id: str,
    session: Session = Depends(get_session),
    _device: MobileReviewDevice = Depends(get_current_device),
) -> dict:
    prompt_service.get_version(session, prompt_id, version_id)
    rows = list(session.scalars(
        select(PromptEvaluation)
        .where(
            PromptEvaluation.prompt_id == prompt_id,
            PromptEvaluation.prompt_version_id == version_id,
        )
        .order_by(PromptEvaluation.created_at.desc(), PromptEvaluation.id.desc())
    ))
    return {"evaluations": [_evaluation_dto(row) for row in rows]}


# ===== V2 客户端冻结契约 =====


@router.post("/{prompt_id}/evaluations", summary="V2 追加评分（版本或整体，原子幂等）")
def create_evaluation_v2(
    prompt_id: str,
    body: MobilePromptEvaluationV2Request,
    session: Session = Depends(get_session),
    device: MobileReviewDevice = Depends(get_current_device),
) -> dict:
    return mobile_v2_service.evaluate_prompt(
        session,
        device_id=device.id,
        prompt_id=prompt_id,
        prompt_version_id=body.prompt_version_id,
        overall_score=body.overall_score,
        dimensions=dict(body.dimensions or {}),
        notes=body.notes,
        client_request_id=body.client_request_id,
    )


@router.get("/evaluations/{client_request_id}", summary="V2 本设备评分回执查询")
def evaluation_receipt(
    client_request_id: str,
    session: Session = Depends(get_session),
    device: MobileReviewDevice = Depends(get_current_device),
) -> dict:
    return mobile_v2_service.evaluation_receipt(
        session, device_id=device.id, client_request_id=client_request_id,
    )


@router.get("/{prompt_id}/review-summary", summary="V2 提示词审核汇总（按版本隔离）")
def review_summary(
    prompt_id: str,
    version_id: str | None = Query(default=None, max_length=64),
    session: Session = Depends(get_session),
    _device: MobileReviewDevice = Depends(get_current_device),
) -> dict:
    return mobile_v2_service.prompt_summary(session, prompt_id, version_id)


@router.get("/{prompt_id}/images", summary="V2 提示词关联图片分页（/mobile 缩略图）")
def review_images(
    prompt_id: str,
    version_id: str | None = Query(default=None, max_length=64),
    cursor: str | None = Query(default=None, max_length=256),
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_session),
    _device: MobileReviewDevice = Depends(get_current_device),
) -> dict:
    return mobile_v2_service.prompt_images(
        session, prompt_id, version_id, cursor=cursor, limit=limit,
    )
