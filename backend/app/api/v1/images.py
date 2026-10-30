"""Images / Gallery API（Phase 2C，规范 §四十四、§四十七、§四十八；Phase 3 §十九/§二十四；Phase 5 导入/引用）。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_storage
from app.api.v1.jobs import check_disk_space, resolve_requested_modules
from app.core.errors import NotFoundError, ValidationError
from app.core.filetypes import MAX_UPLOAD_BYTES, mime_for_suffix
from app.engine.release import ensure_modules_released
from app.schemas.image import (
    ImageBatchStatusRequest,
    ImageBatchStatusResponse,
    ImageBackfillRequest,
    ImageBackfillStatus,
    ImageCleanupPreview,
    ImageCleanupRejectedRequest,
    ImageCleanupResult,
    ImageFavoriteRequest,
    ImageImportDuplicate,
    ImageImportFailure,
    ImageImportItem,
    ImageImportResponse,
    ImageListResponse,
    ImageProvenanceResponse,
    ImageReferencesResponse,
    ImageResponse,
    ImageReviewRequest,
    ImageStatsResponse,
    ImageStatusRequest,
    ImageUpscaleRequest,
    ImageVersionsResponse,
    ImageWorkbenchResponse,
    image_response,
)
from app.schemas.job import JobResponse, job_response
from app.services import (
    cleanup_service,
    image_reference_service,
    image_service,
    job_service,
    thumbnail_service,
)
from app.storage.manager import StorageManager

router = APIRouter(prefix="/images", tags=["images"])


@router.get("", response_model=ImageListResponse,
            summary="图库列表（Phase 0.11 标准分页：page/page_size/sort/status）")
def list_images(
    job_id: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    favorite: bool | None = Query(default=None),
    source: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    search: str | None = Query(default=None, description="按导入文件名搜索"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    status: str | None = Query(default=None, description="新审核状态过滤：NEW/KEEP/FAVORITE/REJECT/ARCHIVED"),
    sort: str = Query(default="created_desc", description="created_desc/created_asc/favorite/size"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=40, ge=1, le=100),
    # 兼容旧调用方（Phase 0.11 前用 limit/offset 一次性拉取）；
    # 一旦提供 limit 即以其为页大小，旧语义不变；否则走标准 page/page_size。
    limit: int | None = Query(default=None, ge=1, le=200, include_in_schema=False),
    offset: int = Query(default=0, ge=0, include_in_schema=False),
    session: Session = Depends(get_session),
) -> ImageListResponse:
    if limit is not None:
        eff_limit = limit
        eff_offset = offset
        eff_page = (offset // limit) + 1 if limit else 1
        eff_page_size = limit
    else:
        eff_limit = page_size
        eff_offset = (page - 1) * page_size
        eff_page = page
        eff_page_size = page_size

    items, total = image_service.list_images(
        session, job_id=job_id, review_status=review_status, favorite=favorite,
        source=source, kind=kind, search=search, date_from=date_from, date_to=date_to,
        status=status, sort=sort, limit=eff_limit, offset=eff_offset,
    )
    has_next = (eff_offset + len(items)) < total
    return ImageListResponse(
        items=[image_response(image) for image in items], total=total,
        page=eff_page, page_size=eff_page_size, has_next=has_next,
    )


@router.get("/ids", summary="按图库筛选返回全部匹配图片 ID（上限 10000）")
def list_image_ids(
    job_id: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    favorite: bool | None = Query(default=None),
    source: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    search: str | None = Query(default=None, description="按导入文件名搜索"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    status: str | None = Query(default=None, description="新审核状态过滤：NEW/KEEP/FAVORITE/REJECT/ARCHIVED"),
    sort: str = Query(default="created_desc", description="created_desc/created_asc/favorite/size"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    limit = image_service.IMAGE_IDS_LIMIT
    ids, total = image_service.list_image_ids(
        session, job_id=job_id, review_status=review_status, favorite=favorite,
        source=source, kind=kind, search=search, date_from=date_from, date_to=date_to,
        status=status, sort=sort, limit=limit,
    )
    return {"ids": ids, "total": total, "truncated": total > limit, "limit": limit}


@router.post("/import", response_model=ImageImportResponse, status_code=201,
             summary="导入外部图片（多张；sha256 去重；单张失败不影响整批）")
async def import_images(
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_session),
    storage: StorageManager = Depends(get_storage),
) -> ImageImportResponse:
    """外部图片（PNG / JPG / JPEG / WEBP）→ 校验 → 复制进 DataRoot/images/originals/ → Gallery。

    - **绝不引用用户原始文件路径**（§五）；source=import，job_id/job_item_id 为 null；
    - sha256 去重（§六）：重复文件不创建第二份，返回已存在的 image_id；
    - 单张失败（非法/超限/损坏）记入 failed 并继续（§二十三），不是生成 Job。
    """
    if not files:
        raise ValidationError("未选择任何文件", code="IMPORT_EMPTY")
    uploads: list[tuple[str | None, str | None, bytes]] = []
    for upload in files:
        data = upload.file.read(MAX_UPLOAD_BYTES + 1)
        uploads.append((upload.filename, upload.content_type, data))
    result = image_service.import_images_batch(session, storage, uploads)
    return ImageImportResponse(
        imported=[ImageImportItem(filename=_display_name(image.imported_filename), image=image_response(image))
                  for image in result.imported],
        duplicates=[ImageImportDuplicate(**item) for item in result.duplicates],
        failed=[ImageImportFailure(**item) for item in result.failed],
        imported_count=len(result.imported),
        duplicate_count=len(result.duplicates),
        failed_count=len(result.failed),
    )


def _display_name(filename: str | None) -> str:
    return filename or "(未命名)"


@router.post("/thumbnails/backfill", response_model=ImageBackfillStatus,
             summary="启动历史缩略图/预览回填（单 worker 低并发，立即返回状态）")
def backfill_thumbnails(request: Request, body: ImageBackfillRequest) -> ImageBackfillStatus:
    """启动（或复用）一个后台回填任务，立即返回状态；同一时间只允许一个回填任务。

    - kind=thumbnail（默认）/preview；limit 限制本次最多补多少张；
    - 重复调用返回当前任务，不重复起；单张失败跳过不阻断；
    - 不占 GPU；Studio 重启后再次调用可重算缺失（进程内状态，无持久化任务）。
    """
    runner = request.app.state.backfill_runner
    return ImageBackfillStatus(**runner.start(kind=body.kind, limit=body.limit))


@router.get("/thumbnails/backfill/status", response_model=ImageBackfillStatus,
            summary="回填任务状态（running/done/total/failed/kind）")
def backfill_thumbnails_status(request: Request) -> ImageBackfillStatus:
    return ImageBackfillStatus(**request.app.state.backfill_runner.status())


@router.post("/thumbnails/backfill/stop", response_model=ImageBackfillStatus,
             summary="请求停止回填（当前张完成后停止），返回最终状态")
def backfill_thumbnails_stop(request: Request) -> ImageBackfillStatus:
    return ImageBackfillStatus(**request.app.state.backfill_runner.stop())


@router.get("/job-groups", summary="按 Job 聚合图库统计与最新四张预览（批量查询，避免 N+1）")
def list_job_groups(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict:
    """只含 completed/有产出图的 Job；按 Job created_at 倒序。

    每个 Job 返回 {job_id, module_id, created_at, total, unreviewed, kept, rejected,
    favorites, preview_image_ids}；预览图按 created_at/id 倒序，计数口径与
    by-job/{job_id}/summary 完全一致。
    """
    groups, total = image_service.list_job_groups(session, page=page, page_size=page_size)
    return {
        "items": groups, "total": total, "page": page, "page_size": page_size,
        "has_next": (page - 1) * page_size + len(groups) < total,
    }


@router.get("/stats", response_model=ImageStatsResponse,
            summary="全局图库统计（与 GET /images 相同过滤口径；SQL 单行聚合）")
def image_stats(
    job_id: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    favorite: bool | None = Query(default=None),
    source: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    search: str | None = Query(default=None, description="按导入文件名搜索"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    status: str | None = Query(default=None, description="新审核状态过滤：NEW/KEEP/FAVORITE/REJECT/ARCHIVED"),
    session: Session = Depends(get_session),
) -> ImageStatsResponse:
    """返回命中过滤条件后的**全局**计数 {total, new, keep, reject, archived, favorites}。

    - 过滤参数与 GET /api/v1/images 完全一致（共用同一套过滤构造，口径绝不漂移）；
    - favorites = favorite=true 的独立交叉计数，不并入任一审核状态；
    - 用于 Gallery 顶部与 ReviewMode 的全局统计（替代"分母 server total、分子本地 list"的假全局）。
    """
    return ImageStatsResponse(**image_service.image_stats(
        session, job_id=job_id, review_status=review_status, favorite=favorite,
        source=source, kind=kind, search=search, date_from=date_from, date_to=date_to,
        status=status,
    ))


@router.get("/{image_id}", response_model=ImageResponse, summary="图片详情")
def get_image(image_id: str, session: Session = Depends(get_session)) -> ImageResponse:
    return image_response(image_service.get_image(session, image_id))


@router.get("/{image_id}/content", summary="图片文件流")
def get_image_content(image_id: str, session: Session = Depends(get_session),
                      storage: StorageManager = Depends(get_storage)) -> FileResponse:
    image = image_service.get_image(session, image_id)
    absolute = storage.absolutize(image.file_path)
    if not absolute.is_file():
        raise NotFoundError("图片文件缺失", code="IMAGE_FILE_MISSING")
    suffix = absolute.suffix.lower()
    return FileResponse(absolute, media_type=mime_for_suffix(suffix))


@router.get("/{image_id}/thumbnail", summary="缩略图（512px WebP q80；缺失则按需生成并落 ImageVariant）")
def get_image_thumbnail(image_id: str, session: Session = Depends(get_session),
                       storage: StorageManager = Depends(get_storage)) -> FileResponse:
    """图库只加载缩略图；Lightbox 才加载 original。

    - 若该图已有 thumbnail variant 且文件在 → 直接返回；
    - 缺失 → 轻量 resize 生成 WebP 并写 ImageVariant 后返回（不阻塞整库）；
    - 历史缺图由回填脚本批量补齐，浏览不依赖回填完成。
    """
    image = image_service.get_image(session, image_id)
    absolute, _variant = thumbnail_service.get_or_create_thumbnail(session, storage, image)
    return FileResponse(absolute, media_type="image/webp")


@router.get("/{image_id}/preview", summary="预览图（长边 1536 WebP q85；缺失则按需生成）")
def get_image_preview(image_id: str, session: Session = Depends(get_session),
                      storage: StorageManager = Depends(get_storage)) -> FileResponse:
    """Review Mode / Lightbox 渐进加载用 preview（比 thumbnail 清晰、比 original 轻量）。

    - 最长边 1536（落在 1280~1600）、WebP q85、仅下采样、保留 alpha；
    - 落 images/previews/<image_id>/preview.webp，并发安全（与 thumbnail 同一生产链）。
    """
    image = image_service.get_image(session, image_id)
    absolute, _variant = thumbnail_service.get_or_create_preview(session, storage, image)
    return FileResponse(absolute, media_type="image/webp")


@router.patch("/{image_id}/review", response_model=ImageResponse, summary="审核状态（保留/淘汰/未审核）")
def review_image(image_id: str, body: ImageReviewRequest, session: Session = Depends(get_session)) -> ImageResponse:
    return image_response(image_service.set_review(session, image_id, body.review_status))


@router.patch("/{image_id}/favorite", response_model=ImageResponse, summary="收藏切换")
def favorite_image(image_id: str, body: ImageFavoriteRequest, session: Session = Depends(get_session)) -> ImageResponse:
    return image_response(image_service.set_favorite(session, image_id, body.favorite))


@router.patch("/{image_id}/status", response_model=ImageResponse,
              summary="新审核状态（NEW/KEEP/FAVORITE/REJECT/ARCHIVED）")
def status_image(image_id: str, body: ImageStatusRequest,
                 session: Session = Depends(get_session)) -> ImageResponse:
    """置 images.status + review_note；除 NEW 外置 reviewed_at。

    FAVORITE 同步 favorite=1，离开 FAVORITE 同步 favorite=0（语义一致）。
    """
    return image_response(image_service.set_image_status(session, image_id, body.status, body.note))


@router.post("/batch-status", response_model=ImageBatchStatusResponse,
             summary="批量审核（同一状态批量应用到多张图）")
def batch_status_images(body: ImageBatchStatusRequest,
                       session: Session = Depends(get_session)) -> ImageBatchStatusResponse:
    images = image_service.batch_set_status(session, body.image_ids, body.status, body.note)
    return ImageBatchStatusResponse(
        updated=len(images), items=[image_response(image) for image in images]
    )


@router.post("/cleanup-rejected",
             summary="废片清理（REJECT；两阶段：confirm 非 true 仅预览，true 才真删）")
def cleanup_rejected(body: ImageCleanupRejectedRequest,
                    session: Session = Depends(get_session),
                    storage: StorageManager = Depends(get_storage)
                    ) -> ImageCleanupPreview | ImageCleanupResult:
    """REJECT 图两阶段清理：

    - confirm != true → 预览 {candidate_count, total_bytes(预计释放), protected_count}，不删除；
    - confirm == true → 删除未受保护的 REJECT 图的 original+全部 variants 文件与 DB 记录；
      被 Prompt/Asset/Recipe/派生图/活跃 Job 引用的图跳过并计入 protected，绝不留悬空。
    """
    ids = body.image_ids or None
    if not body.confirm:
        return ImageCleanupPreview(**cleanup_service.preview(session, storage, ids))
    return ImageCleanupResult(**cleanup_service.execute(session, storage, ids))


@router.get("/{image_id}/workbench", response_model=ImageWorkbenchResponse,
            summary="Image → 生成工作台（Phase 6 Task1：最近的生成上下文 Job；Task9 携带完整执行身份）")
def image_to_workbench(image_id: str, session: Session = Depends(get_session)) -> ImageWorkbenchResponse:
    """任何派生图都恢复到**最近的生成上下文**（Phase 6 Task1）。

    - 从当前图沿 parent_image_id 向上找"距离最近、由 generate Job 产出、且使用 Seed"的图；
      import→img2img→upscale 恢复 Img2Img（不是树根的导入图）；basic→upscale 恢复 basic；
    - 禁止恢复 process Job（图库高清）的空 Prompt；
    - 外部导入图（全链无生成上下文）→ IMAGE_NO_GENERATION_CONTEXT（"没有可恢复的生成配置"）；
    - seed 返回**生成上下文图片的真实 Seed**（"使用此图 Seed"）；快照 Seed 默认 random；
    - workflow_modules 覆盖为上下文 Job 的完整执行身份（Task9：module/version/provider/binding/双指纹），
      提交时按原版本精确重现，绝不偷偷升级到当前默认 Workflow。
    """
    image = image_service.get_image(session, image_id)
    context, job = image_service.resolve_generation_context(session, image)
    snapshot = json.loads(job.workbench_snapshot_json or "{}")
    modules = json.loads(job.workflow_snapshot_json or "{}").get("modules") or []
    if not modules and job.module_id:
        # 极老 Job 的 workflow_snapshot 为空：回落到 Job 列上的执行身份
        modules = [{
            "module_id": job.module_id, "module_version": job.module_version,
            "provider": job.provider, "binding_version": job.binding_version,
            "workflow_hash": job.workflow_hash, "binding_hash": job.binding_hash,
        }]
    snapshot["workflow_modules"] = modules
    snapshot["seed_mode"] = "random"
    snapshot["seed"] = None
    return ImageWorkbenchResponse(image_id=image.id, seed=context.seed, snapshot=snapshot)


@router.get("/{image_id}/provenance", response_model=ImageProvenanceResponse,
            summary="Image Provenance（Task10）：来源任务 / Stage / 模块 / 双指纹 / Seed")
def image_provenance(image_id: str, session: Session = Depends(get_session)) -> ImageProvenanceResponse:
    return ImageProvenanceResponse(**image_service.get_provenance(session, image_id))


@router.get("/{image_id}/references", response_model=ImageReferencesResponse,
            summary="图片引用检查（Phase 5 §十一）：删除前知道仍被哪些对象引用")
def image_references(image_id: str, session: Session = Depends(get_session)) -> ImageReferencesResponse:
    return ImageReferencesResponse(**image_reference_service.count_references(session, image_id))


@router.post("/upscale", response_model=JobResponse, status_code=201,
             summary="图库图片高清放大（创建处理型 Job，§二十/§二十四）")
def upscale_images(request: Request, body: ImageUpscaleRequest,
                   session: Session = Depends(get_session),
                   storage: StorageManager = Depends(get_storage)) -> JobResponse:
    """选择已有图片（1 张或多张）→ 创建 job_kind=process 的普通 Job，由同一 QueueWorker 执行。

    绝不在此直接调用引擎；Pipeline = upscale（不重跑基础生成，§二十）。
    """
    disk = check_disk_space(request)
    settings = request.app.state.settings
    image_ids = list(dict.fromkeys(body.image_ids))  # 去重且保持选择顺序
    images = [image_service.get_image(session, image_id) for image_id in image_ids]
    for image in images:
        if not storage.absolutize(image.file_path).is_file():
            raise ValidationError(f"图片文件缺失，无法放大: {image.id}", code="IMAGE_FILE_MISSING")

    modules = resolve_requested_modules(settings, [{"module_id": "upscale"}])
    ensure_modules_released(modules)
    first = images[0]
    snapshot = {
        "prompt_mode": "structured",
        "structured_prompt": {},
        "full_prompt": "",
        "negative_prompt": "",
        "selected_assets": {},
        "width": first.width,
        "height": first.height,
        "count": len(images),
        "seed_mode": "random",
        "seed": None,
        "workflow_modules": [{"module_id": "upscale"}],
    }
    job, _created = job_service.create_job(
        session,
        source="web",
        snapshot=snapshot,
        workflow_modules=modules,
        job_kind="process",
        input_image_ids=image_ids,
    )
    response = job_response(job)
    response.disk_space = disk
    return response


@router.get("/{image_id}/versions", response_model=ImageVersionsResponse,
            summary="父子关系（§十九）：派生版本 / 来源原图")
def image_versions(image_id: str, session: Session = Depends(get_session)) -> ImageVersionsResponse:
    versions = image_service.get_versions(session, image_id)
    return ImageVersionsResponse(
        image=image_response(versions["image"]),
        parent=image_response(versions["parent"]) if versions["parent"] is not None else None,
        children=[image_response(child) for child in versions["children"]],
    )


@router.get("/by-job/{job_id}/summary", summary="按 Job 统计（规范 §四十九）")
def job_summary(job_id: str, session: Session = Depends(get_session)) -> dict:
    return image_service.job_gallery_summary(session, job_id)
