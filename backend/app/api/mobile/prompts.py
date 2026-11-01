"""W3.0 Mobile Prompt Version 评分（Bearer + 幂等）。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.mobile.deps import get_current_device, get_session
from app.models import PromptEvaluation
from app.models.mobile_review import MobileReviewDevice
from app.schemas.prompt import EvaluationDimension, EvaluationScore, PromptEvaluationCreateRequest
from app.services import mobile_mutation_service, prompt_scoring_service, prompt_service

router = APIRouter(prefix="/mobile/prompts", tags=["mobile-prompts"])


class MobilePromptEvaluationRequest(BaseModel):
    overall_score: EvaluationScore
    dimension_scores: dict[EvaluationDimension, EvaluationScore] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=2000)


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
    summary="Prompt 版本评分（幂等，source=mobile；不改 Prompt 状态）",
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
    operation = f"prompt_evaluation:{prompt_id}:{version_id}"
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
    summary="查询指定 Prompt Version 的评分记录",
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
