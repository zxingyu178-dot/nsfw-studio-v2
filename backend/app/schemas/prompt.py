"""Prompt 相关出入参。"""
import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models import Prompt, PromptEvaluation, PromptVersion
from app.schemas.image import ImageResponse
from app.schemas.workbench import PromptMode, StructuredPromptModel, structured_model_from_json


class PromptCreateRequest(BaseModel):
    name: str
    mode: PromptMode = "structured"
    positive_prompt: str = ""
    negative_prompt: str = ""
    structured: StructuredPromptModel = Field(default_factory=StructuredPromptModel)
    favorite: bool = False


class PromptMetaUpdateRequest(BaseModel):
    name: str | None = None
    favorite: bool | None = None


class PromptEnsureRequest(BaseModel):
    """AI 提交前的提示词入库请求：同一段提示词已有则复用，否则自动新建。"""

    positive_prompt: str
    negative_prompt: str = ""
    name: str | None = None


class PromptEnsureResponse(BaseModel):
    prompt_id: str
    version_id: str
    created: bool


class PreviewImageRequest(BaseModel):
    image_id: str


class PromptVersionCreateRequest(BaseModel):
    mode: PromptMode = "structured"
    positive_prompt: str = ""
    negative_prompt: str = ""
    structured: StructuredPromptModel = Field(default_factory=StructuredPromptModel)


class ComposeRequest(BaseModel):
    mode: PromptMode = "structured"
    positive_prompt: str = ""
    structured: StructuredPromptModel = Field(default_factory=StructuredPromptModel)


class ComposeResponse(BaseModel):
    composed_prompt: str


class PromptVersionResponse(BaseModel):
    id: str
    prompt_id: str
    version_no: int
    mode: str
    positive_prompt: str
    negative_prompt: str
    structured: StructuredPromptModel
    created_at: str


PromptStatus = Literal["keep", "candidate", "eliminated"]
EvaluationDimension = Literal["subject", "clothing", "scene", "composition", "lighting", "style", "quality"]
EvaluationScore = Annotated[int, Field(strict=True, ge=1, le=5)]


class PromptEvaluationCreateRequest(BaseModel):
    overall_score: EvaluationScore
    dimension_scores: dict[EvaluationDimension, EvaluationScore] = Field(default_factory=dict)
    notes: str = ""
    prompt_version_id: str | None = None


class PromptEvaluationResponse(BaseModel):
    id: str
    prompt_id: str
    prompt_version_id: str | None
    overall_score: EvaluationScore
    dimension_scores: dict[EvaluationDimension, EvaluationScore]
    source: str
    notes: str
    created_at: str


class PromptStatusRequest(BaseModel):
    status: PromptStatus
    reason: str = ""


class PromptResponse(BaseModel):
    id: str
    name: str
    favorite: bool
    archived: bool
    preview_image_id: str | None
    created_at: str
    updated_at: str
    current_version: PromptVersionResponse | None
    status: PromptStatus = "candidate"
    status_reason: str = ""


class PromptImageResponse(ImageResponse):
    job_status: str
    module_id: str | None
    thumbnail_url: str
    preview_url: str


class PromptImagesResponse(BaseModel):
    items: list[PromptImageResponse]
    total: int
    limit: int
    offset: int


class PromptListItemResponse(PromptResponse):
    latest_evaluation: PromptEvaluationResponse | None = None
    images: list[PromptImageResponse] | None = None
    images_total: int | None = None


class PromptListResponse(BaseModel):
    items: list[PromptListItemResponse]
    total: int
    limit: int
    offset: int


def prompt_version_response(version: PromptVersion) -> PromptVersionResponse:
    return PromptVersionResponse(
        id=version.id,
        prompt_id=version.prompt_id,
        version_no=version.version_no,
        mode=version.mode,
        positive_prompt=version.positive_prompt,
        negative_prompt=version.negative_prompt,
        structured=structured_model_from_json(version.structured_json),
        created_at=version.created_at,
    )


def prompt_response(prompt: Prompt, current_version: PromptVersion | None) -> PromptResponse:
    return PromptResponse(
        id=prompt.id,
        name=prompt.name,
        favorite=prompt.favorite,
        archived=prompt.archived,
        status=prompt.status,
        status_reason=prompt.status_reason,
        preview_image_id=prompt.preview_image_id,
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
        current_version=prompt_version_response(current_version) if current_version else None,
    )


def prompt_evaluation_response(evaluation: PromptEvaluation) -> PromptEvaluationResponse:
    return PromptEvaluationResponse(
        id=evaluation.id, prompt_id=evaluation.prompt_id,
        prompt_version_id=evaluation.prompt_version_id,
        overall_score=evaluation.overall_score,
        dimension_scores=json.loads(evaluation.dimension_scores_json),
        source=evaluation.source, notes=evaluation.notes, created_at=evaluation.created_at,
    )
