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
from app.schemas.image import (
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
    ImageUpscaleRequest,
    ImageVersionsResponse,
    ImageWorkbenchResponse,
    image_response,
)
from app.schemas.job import JobResponse, job_response
from app.services import image_reference_service, image_service, job_service
from app.storage.manager import StorageManager

router = APIRouter(prefix="/images", tags=["images"])


@router.get("", response_model=ImageListResponse, summary="图库列表（job/review/favorite/source/date 过滤）")
def list_images(
    job_id: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    favorite: bool | None = Query(default=None),
    source: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    search: str | None = Query(default=None, description="按导入文件名搜索"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> ImageListResponse:
    items, total = image_service.list_images(
        session, job_id=job_id, review_status=review_status, favorite=favorite,
        source=source, kind=kind, search=search, date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
    )
    return ImageListResponse(
        items=[image_response(image) for image in items], total=total, limit=limit, offset=offset
    )


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


@router.patch("/{image_id}/review", response_model=ImageResponse, summary="审核状态（保留/淘汰/未审核）")
def review_image(image_id: str, body: ImageReviewRequest, session: Session = Depends(get_session)) -> ImageResponse:
    return image_response(image_service.set_review(session, image_id, body.review_status))


@router.patch("/{image_id}/favorite", response_model=ImageResponse, summary="收藏切换")
def favorite_image(image_id: str, body: ImageFavoriteRequest, session: Session = Depends(get_session)) -> ImageResponse:
    return image_response(image_service.set_favorite(session, image_id, body.favorite))


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
