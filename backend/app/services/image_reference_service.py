"""ImageReferenceService（Phase 5 §十一：图片生命周期引用保护）。

用途：物理删除 / 清理图片之前，回答"这张图片仍被哪些对象引用"。
Phase 5 不实现完整删除 UI，只提供确定性检查（删除前可知道引用数量与类型）。

引用来源（与合同 §十一 对齐）：
- Recipe：recipe_versions.input_images_json 中引用了该 image_id（任一版本）；
- JobStageItem：job_stage_items.input_image_id（等待 / 运行 / 历史 Job 的输入冻结）；
- Asset Reference：asset_reference_images.image_id（Face Asset 参考图关系表）；
- Derived Image：images.parent_image_id（派生图挂在该图下）；
- Asset 溯源：assets.source_image_id（从图库创建的素材记录了来源）。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Asset,
    AssetReferenceImage,
    AssetVersion,
    Image,
    Job,
    JobStage,
    JobStageItem,
    Recipe,
    RecipeVersion,
)
from app.services.image_service import get_image

ACTIVE_JOB_STATUSES = ("QUEUED", "RUNNING", "PAUSED", "INTERRUPTED")


def count_references(session: Session, image_id: str) -> dict:
    """统计图片的全部引用（删除前检查；找不到图片时抛 IMAGE_NOT_FOUND）。"""
    get_image(session, image_id)  # 存在性校验

    # 1) Recipe（任一版本的输入图快照）
    recipe_rows = session.execute(
        select(RecipeVersion.recipe_id)
        .where(RecipeVersion.input_images_json.like(f'%"{image_id}"%'))
    ).scalars().all()
    recipe_ids = sorted(set(recipe_rows))

    # 2) JobStageItem（输入冻结）；附带活跃 Job 集合
    stage_item_rows = session.execute(
        select(JobStageItem.id, Job.id, Job.status)
        .join(JobStage, JobStage.id == JobStageItem.job_stage_id)
        .join(Job, Job.id == JobStage.job_id)
        .where(JobStageItem.input_image_id == image_id)
    ).all()
    stage_item_ids = [row[0] for row in stage_item_rows]
    job_ids = sorted({row[1] for row in stage_item_rows})
    active_job_ids = sorted({row[1] for row in stage_item_rows if row[2] in ACTIVE_JOB_STATUSES})

    # 3) Asset Reference（关系表）与 Asset 溯源（source_image_id）
    asset_reference_rows = session.execute(
        select(AssetReferenceImage.asset_version_id, AssetVersion.asset_id)
        .join(AssetVersion, AssetVersion.id == AssetReferenceImage.asset_version_id)
        .where(AssetReferenceImage.image_id == image_id)
    ).all()
    reference_asset_ids = sorted({row[1] for row in asset_reference_rows})
    source_asset_ids = sorted(session.execute(
        select(Asset.id).where(Asset.source_image_id == image_id)
    ).scalars().all())

    # 4) Derived Image（派生图 parent 指向该图）
    derived_image_ids = sorted(session.execute(
        select(Image.id).where(Image.parent_image_id == image_id)
    ).scalars().all())

    references = {
        "recipe_ids": recipe_ids,
        "stage_item_ids": stage_item_ids,
        "job_ids": job_ids,
        "reference_asset_ids": reference_asset_ids,
        "source_asset_ids": source_asset_ids,
        "derived_image_ids": derived_image_ids,
    }
    total = (
        len(recipe_ids) + len(stage_item_ids) + len(reference_asset_ids)
        + len(source_asset_ids) + len(derived_image_ids)
    )
    return {
        "image_id": image_id,
        "total": total,
        "active_job_ids": active_job_ids,
        "references": references,
    }