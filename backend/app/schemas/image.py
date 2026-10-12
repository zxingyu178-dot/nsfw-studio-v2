"""Image / Gallery 相关出入参。"""
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models import IMAGE_STATUSES, Image
import json

ReviewStatus = Literal["UNREVIEWED", "KEPT", "REJECTED"]
# Phase 0.11 新审核体系（images.status）
ImageStatus = Literal["NEW", "KEEP", "FAVORITE", "REJECT", "ARCHIVED"]
# Phase 0.11 图库分页排序枚举（合同冻结）
ImageSort = Literal["created_desc", "created_asc", "favorite", "size"]


class ImageReviewRequest(BaseModel):
    review_status: ReviewStatus


class ImageFavoriteRequest(BaseModel):
    favorite: bool


class ImageStatusRequest(BaseModel):
    """Phase 0.11：PATCH /images/{id}/status 入参。

    status 为新审核体系状态；note 可选审核备注（写 images.review_note）。
    """

    status: ImageStatus
    note: str | None = None


class ImageBatchStatusRequest(BaseModel):
    """Phase 0.11：POST /images/batch-status 入参（批量审核）。"""

    image_ids: list[str] = Field(min_length=1, max_length=500)
    status: ImageStatus
    note: str | None = None


class ImageBatchStatusResponse(BaseModel):
    updated: int
    items: list["ImageResponse"]


class ImageCleanupRejectedRequest(BaseModel):
    """Phase 0.11：POST /images/cleanup-rejected 入参。

    image_ids 为空 → 作用于全部 REJECT 图；confirm 非 True → 仅预览不删除。
    """

    image_ids: list[str] = Field(default_factory=list, max_length=1000)
    confirm: bool = False


class ImageBackfillRequest(BaseModel):
    """Phase 0.11.1：POST /images/thumbnails/backfill 入参。

    kind=thumbnail（默认）/preview；limit 限制本次最多补多少张（上限 2000）。
    """

    kind: Literal["thumbnail", "preview"] = "thumbnail"
    limit: int | None = Field(default=None, ge=1, le=2000)


class ImageBackfillStatus(BaseModel):
    """回填任务状态：total=待处理总数、done=完成、failed=失败跳过数。"""

    running: bool
    done: int
    total: int
    failed: int
    kind: Literal["thumbnail", "preview"]


class ImageCleanupProtectedItem(BaseModel):
    """Phase 0.11.1：被引用保护而跳过的单图及原因摘要。"""

    image_id: str
    reasons: list[str]


class ImageCleanupPreview(BaseModel):
    # 向后兼容保留 candidate_count / total_bytes / protected_count
    candidate_count: int
    deletable_count: int
    protected_count: int
    total_bytes: int
    protected_items: list[ImageCleanupProtectedItem]


class ImageCleanupResult(BaseModel):
    deleted_count: int
    deleted_bytes: int
    protected_count: int
    deletable_count: int
    failed: list[dict[str, Any]]


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
    # Phase 0.11 新审核体系（0016）
    status: str
    reviewed_at: str | None
    review_note: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


class ImageListResponse(BaseModel):
    """Phase 0.11 标准分页响应（合同冻结：items/total/page/page_size/has_next）。"""

    items: list[ImageResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class ImageStatsResponse(BaseModel):
    """Phase 0.12 全局图库统计（与 GET /images 完全相同的过滤口径；SQL 单行聚合）。

    用于修正 ReviewMode "分母=server total、分子=本地已加载 list" 的假全局统计：
    各状态计数与收藏计数都是命中过滤条件后的**全局**数字。
    favorites 是 favorite=true 的独立交叉计数（不并入任一审核状态）。
    """

    total: int
    new: int
    keep: int
    reject: int
    archived: int
    favorites: int


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
    """Image → 生成工作台（规范 §四十七；Phase 4 Task7/9；Phase 6 Task1）。

    追溯规则（Phase 6 Task1）：任何派生图都恢复到**最近的生成上下文**——从当前图沿
    parent_image_id 向上找"距离最近、由 generate Job 产出、且使用 Seed"的图及其 Job
    （import→img2img→upscale 恢复 Img2Img，而不是树根的导入图）。
    seed 为该生成上下文图片的**真实 Seed**（"使用此图 Seed"由前端显式固定；默认 random）。
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
    # Phase 0.12 Task12：工作台最初从哪个 Recipe 打开（轻量 provenance；None=非 Recipe 来源）
    source_recipe_id: str | None
    source_recipe_version_id: str | None


def image_response(image: Image) -> ImageResponse:
    return ImageResponse(
        id=image.id, job_id=image.job_id, job_item_id=image.job_item_id,
        parent_image_id=image.parent_image_id, kind=image.kind, file_path=image.file_path,
        width=image.width, height=image.height, seed=image.seed,
        review_status=image.review_status, favorite=image.favorite, source=image.source,
        status=image.status, reviewed_at=image.reviewed_at, review_note=image.review_note or "",
        metadata=json.loads(image.metadata_json or "{}"),
        created_at=image.created_at, updated_at=image.updated_at,
    )
