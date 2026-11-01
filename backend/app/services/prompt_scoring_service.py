"""提示词人工评分与状态管理；评分不自动淘汰，也不改动内容版本。"""
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.ids import PROMPT_EVALUATION, new_id
from app.models import Prompt, PromptEvaluation
from app.schemas.prompt import PromptEvaluationCreateRequest, PromptStatusRequest
from app.services import image_event_service, prompt_service


def create_evaluation(
    session: Session, prompt_id: str, request: PromptEvaluationCreateRequest,
    *, source: str = "user", commit: bool = True,
) -> PromptEvaluation:
    prompt_service.get_prompt(session, prompt_id)
    if request.prompt_version_id is not None:
        prompt_service.get_version(session, prompt_id, request.prompt_version_id)
    evaluation = PromptEvaluation(
        id=new_id(PROMPT_EVALUATION), prompt_id=prompt_id,
        prompt_version_id=request.prompt_version_id, overall_score=request.overall_score,
        dimension_scores_json=json.dumps(request.dimension_scores, ensure_ascii=False),
        source=source, notes=request.notes,
    )
    try:
        session.add(evaluation)
        session.flush()
        # W3.0：评分与 PROMPT_EVALUATED 事件同一事务；默认 commit 保持 Desktop 旧行为。
        image_event_service.record_prompt_evaluated(session, evaluation)
        if commit:
            session.commit()
    except Exception:
        session.rollback()
        raise
    return evaluation


def list_evaluations(session: Session, prompt_id: str) -> list[PromptEvaluation]:
    prompt_service.get_prompt(session, prompt_id)
    return list(session.scalars(
        select(PromptEvaluation).where(PromptEvaluation.prompt_id == prompt_id)
        .order_by(PromptEvaluation.created_at.desc(), PromptEvaluation.id.desc()),
    ))


def set_status(session: Session, prompt_id: str, request: PromptStatusRequest) -> Prompt:
    prompt = prompt_service.get_prompt(session, prompt_id)
    prompt.status = request.status
    prompt.status_reason = request.reason
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    return prompt


def latest_evaluations(session: Session, prompt_ids: list[str]) -> dict[str, PromptEvaluation]:
    """每个提示词只返回最新一条，查询次数与提示词数量、历史评分数量无关。"""
    if not prompt_ids:
        return {}
    ranked = select(
        PromptEvaluation.id,
        func.row_number().over(
            partition_by=PromptEvaluation.prompt_id,
            order_by=(PromptEvaluation.created_at.desc(), PromptEvaluation.id.desc()),
        ).label("position"),
    ).where(PromptEvaluation.prompt_id.in_(prompt_ids)).subquery()
    rows = session.scalars(
        select(PromptEvaluation).join(ranked, ranked.c.id == PromptEvaluation.id)
        .where(ranked.c.position == 1),
    )
    return {evaluation.prompt_id: evaluation for evaluation in rows}
