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


class ImageImportItem(BaseModel):
    """成功导入的图片（含原始文件名）。"""

    filename: str
    image: ImageResponse


class ImageImportDuplicate(BaseModel):
    """重复文件（sha256 已存在）：不创建第二份，返回已存在的 image_id。"""

    filename: str
    image_id: str
    sha256: str


class ImageImportFailure(BaseModel):
    """单张失败明细（§二十三：部分失败不影响整批）。"""

    filename: str
    error_code: str
    message: str


class ImageImportResponse(BaseModel):
    imported: list[ImageImportItem]
    duplicates: list[ImageImportDuplicate]
    failed: list[ImageImportFailure]
    imported_count: int
    duplicate_count: int
    failed_count: int


class ImageReferencesResponse(BaseModel):
    """图片引用保护检查（Task11/§十一：删除前知道仍被哪些对象引用）。"""

    image_id: str
    total: int
    active_job_ids: list[str]
    references: dict[str, list[str]]


class ImageWorkbenchResponse(BaseModel):
    """Image → 生成工作台（规范 §四十七；Phase 4 Task7/9）。

    追溯规则（Task7）：任何派生图都恢复到**根生成图所属 generate Job** 的 WorkbenchSnapshot；
    seed 为根图的 Seed（"使用原图 Seed" 由前端显式固定；默认 random）。
    快照中的 workflow_modules 携带**完整执行身份**（Task9），提交时按原版本精确重现。
    """

    image_id: str
    seed: int | None
    snapshot: dict[str, Any]


class ImageProvenanceResponse(BaseModel):
    """Image Provenance（Task10）：图片完整溯源（前端默认简洁展示，高级信息折叠）。"""

    image_id: str
    kind: str
    parent_image_id: str | None
    root_image_id: str
    scale: int | None  # 相对来源原图的倍率（如高清 ×4）
    job_id: str | None
    job_item_id: str | None
    stage_id: str | None
    stage_index: int | None
    stage_item_id: str | None
    module_id: str | None
    module_version: str | None
    provider: str | None
    binding_version: str | None
    workflow_hash: str | None
    binding_hash: str | None
    seed: int | None


def image_response(image: Image) -> ImageResponse:
    return ImageResponse(
        id=image.id, job_id=image.job_id, job_item_id=image.job_item_id,
        parent_image_id=image.parent_image_id, kind=image.kind, file_path=image.file_path,
        width=image.width, height=image.height, seed=image.seed,
        review_status=image.review_status, favorite=image.favorite, source=image.source,
        metadata=json.loads(image.metadata_json or "{}"),
        created_at=image.created_at, updated_at=image.updated_at,
    )
