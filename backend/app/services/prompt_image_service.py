"""提示词图片只读查询：按生成 Job 的来源快照归属，不遍历任务项。"""
from collections.abc import Sequence

from sqlalchemy import String, cast, func, literal, select, true
from sqlalchemy.orm import Session

from app.models import Image, Job, PromptVersion
from app.schemas.image import image_response
from app.schemas.prompt import (
    PromptImageResponse, PromptImagesResponse, PromptListItemResponse,
    PromptListResponse, prompt_evaluation_response, prompt_response,
)
from app.services import prompt_scoring_service, prompt_service


def _source_prompt_id():
    return func.json_extract(Job.workbench_snapshot_json, "$.source_prompt_id")


def _prompt_image_links(*, prompt_id: str | None = None, version_id: str | None = None):
    """合并 Job 快照与 V1 导入元数据中的提示词归属。"""
    job_prompt_id = _source_prompt_id()
    job_links = select(
        Image.id.label("image_id"),
        job_prompt_id.label("prompt_id"),
        Job.status.label("job_status"),
        Job.module_id.label("module_id"),
    ).join(Job, Image.job_id == Job.id)
    if prompt_id is not None:
        job_links = job_links.where(job_prompt_id == prompt_id)
    if version_id is not None:
        job_links = job_links.where(
            func.json_extract(Job.workbench_snapshot_json, "$.source_prompt_version_id") == version_id,
        )

    imported_prompt = func.json_each(
        Image.metadata_json, "$.v1_output.prompts",
    ).table_valued("key", "value").alias("imported_prompt")
    imported_prompt_id = func.json_extract(imported_prompt.c.value, "$.prompt_id")
    imported_links = select(
        Image.id.label("image_id"),
        imported_prompt_id.label("prompt_id"),
        literal("IMPORTED").label("job_status"),
        cast(literal(None), String).label("module_id"),
    ).select_from(Image).join(imported_prompt, true()).where(Image.source == "import")
    if prompt_id is not None:
        imported_links = imported_links.where(imported_prompt_id == prompt_id)
    if version_id is not None:
        imported_links = imported_links.where(
            func.json_extract(imported_prompt.c.value, "$.version_id") == version_id,
        )

    # 导入元数据若意外重复同一个提示词记录，也只把图片计入一次。
    return job_links.union_all(imported_links.distinct()).subquery()


def _image_response(image: Image, job_status: str, module_id: str | None) -> PromptImageResponse:
    base = image_response(image)
    return PromptImageResponse(
        **base.model_dump(), job_status=job_status,
        # 多阶段图片的生成模块保存在图片元数据中，旧记录回退到 Job。
        module_id=base.metadata.get("module_id") or module_id,
        thumbnail_url=f"/api/v1/images/{image.id}/thumbnail",
        preview_url=f"/api/v1/images/{image.id}/preview",
    )


def list_prompt_images(
    session: Session, prompt_id: str, *, limit: int = 50, offset: int = 0,
    version_id: str | None = None,
) -> PromptImagesResponse:
    prompt_service.get_prompt(session, prompt_id)
    if version_id is not None:
        prompt_service.get_version(session, prompt_id, version_id)
    links = _prompt_image_links(prompt_id=prompt_id, version_id=version_id)
    query = select(Image, links.c.job_status, links.c.module_id).join(
        links, links.c.image_id == Image.id,
    )
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.execute(query.order_by(Image.created_at.desc(), Image.id.desc()).limit(limit).offset(offset))
    return PromptImagesResponse(
        items=[_image_response(*row) for row in rows], total=total, limit=limit, offset=offset,
    )


def _batch_images(session: Session, prompt_ids: list[str], limit: int):
    """同一次 SQL 计算每组总数并截取最近 N 张；数据库不会返回全部历史图片。"""
    links = _prompt_image_links()
    ranked = select(
        Image.id.label("image_id"), links.c.prompt_id,
        links.c.job_status, links.c.module_id,
        func.count().over(partition_by=links.c.prompt_id).label("total"),
        func.row_number().over(
            partition_by=links.c.prompt_id, order_by=(Image.created_at.desc(), Image.id.desc()),
        ).label("position"),
    ).join(links, links.c.image_id == Image.id).where(links.c.prompt_id.in_(prompt_ids)).subquery()
    rows = session.execute(
        select(Image, ranked.c.prompt_id, ranked.c.job_status, ranked.c.module_id, ranked.c.total)
        .join(ranked, ranked.c.image_id == Image.id)
        .where(ranked.c.position <= limit)
        .order_by(ranked.c.prompt_id, ranked.c.position)
    )
    result = {prompt_id: ([], 0) for prompt_id in prompt_ids}
    for image, prompt_id, job_status, module_id, total in rows:
        images, _ = result[prompt_id]
        images.append(_image_response(image, job_status, module_id))
        result[prompt_id] = (images, total)
    return result


def list_prompts(
    session: Session, *, search: str | None = None, favorite: bool | None = None,
    archived: bool | None = False, limit: int = 50, offset: int = 0,
    include_images: bool = False, images_limit: int = 3,
    include_evaluation: bool = False,
    sort: str = "updated_desc", status: Sequence[str] | None = None,
    scored: bool | None = None,
) -> PromptListResponse:
    prompts, total = prompt_service.list_prompts(
        session, search=search, favorite=favorite, archived=archived, limit=limit, offset=offset,
        sort=sort, status=status, scored=scored,
    )
    # 当前版本也批量读取，避免列表已有的逐提示词查询随数量增长。
    version_ids = [prompt.current_version_id for prompt in prompts if prompt.current_version_id]
    versions = {
        version.id: version for version in session.scalars(
            select(PromptVersion).where(PromptVersion.id.in_(version_ids)),
        )
    } if version_ids else {}
    images = _batch_images(session, [prompt.id for prompt in prompts], images_limit) if include_images and prompts else {}
    evaluations = prompt_scoring_service.latest_evaluations(
        session, [prompt.id for prompt in prompts],
    ) if include_evaluation else {}
    items = []
    for prompt in prompts:
        data = prompt_response(prompt, versions.get(prompt.current_version_id)).model_dump()
        if include_evaluation:
            evaluation = evaluations.get(prompt.id)
            data["latest_evaluation"] = prompt_evaluation_response(evaluation) if evaluation else None
        if include_images:
            data["images"], data["images_total"] = images[prompt.id]
        items.append(PromptListItemResponse(**data))
    return PromptListResponse(items=items, total=total, limit=limit, offset=offset)
