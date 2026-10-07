"""Prompt 相关出入参。"""
from pydantic import BaseModel, Field

from app.models import Prompt, PromptVersion
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


class PromptResponse(BaseModel):
    id: str
    name: str
    favorite: bool
    archived: bool
    created_at: str
    updated_at: str
    current_version: PromptVersionResponse | None


class PromptListResponse(BaseModel):
    items: list[PromptResponse]
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
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
        current_version=prompt_version_response(current_version) if current_version else None,
    )
