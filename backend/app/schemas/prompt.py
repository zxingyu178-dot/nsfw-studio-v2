"""Prompt 相关出入参。"""
from pydantic import BaseModel, Field

from app.models import Prompt, PromptVersion
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


class PromptResponse(BaseModel):
    id: str
    name: str
    favorite: bool
    archived: bool
    preview_image_id: str | None
    created_at: str
    updated_at: str
    current_version: PromptVersionResponse | None


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
        preview_image_id=prompt.preview_image_id,
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
        current_version=prompt_version_response(current_version) if current_version else None,
    )
