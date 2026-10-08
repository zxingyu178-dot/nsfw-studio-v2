"""Image / Gallery 相关出入参。"""
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models import Image
import json

ReviewStatus = Literal["UNREVIEWED", "KEPT", "REJECTED"]


class ImageReviewRequest(BaseModel):
    review_status: ReviewStatus


class ImageFavoriteRequest(BaseModel):
    favorite: bool


class ImageUpscaleRequest(BaseModel):
    """图库高清放大请求（§二十四）：选择 1 张或多张已有图片创建处理型 Job。"""

    image_ids: list[str] = Field(min_length=1, max_length=64)


class ImageVersionsResponse(BaseModel):
    """父子关系（§十九）：原图 → 派生版本（高清等）/ 高清图 → 来源原图。"""

    image: "ImageResponse"
    parent: "ImageResponse | None"
    children: list["ImageResponse"]


class ImageResponse(BaseModel):
    id: str
    job_id: str | None
    job_item_id: str | None
    parent_image_id: str | None
    kind: str
    file_path: str
    width: int
    height: int
    seed: int | None
    review_status: str
    favorite: bool
    source: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


class ImageListResponse(BaseModel):
    items: list[ImageResponse]
    total: int
    limit: int
    offset: int


class ImageWorkbenchResponse(BaseModel):
    """Image → 生成工作台（规范 §四十七）：恢复 Job 当时的 WorkbenchSnapshot。"""

    image_id: str
    seed: int | None
    snapshot: dict[str, Any]


def image_response(image: Image) -> ImageResponse:
    return ImageResponse(
        id=image.id, job_id=image.job_id, job_item_id=image.job_item_id,
        parent_image_id=image.parent_image_id, kind=image.kind, file_path=image.file_path,
        width=image.width, height=image.height, seed=image.seed,
        review_status=image.review_status, favorite=image.favorite, source=image.source,
        metadata=json.loads(image.metadata_json or "{}"),
        created_at=image.created_at, updated_at=image.updated_at,
    )
