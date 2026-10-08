"""数据库模型层。

Phase 0：SystemInfo；
Phase 1：Prompt / PromptVersion、Asset / AssetVersion、Recipe / RecipeVersion / RecipeAssetSnapshot；
Phase 2：Job / JobItem / JobEvent、Image；
Phase 3：JobStage / JobStageItem（多阶段管线）。详见 docs/DATA_MODEL_V1.md。
"""
from app.models.asset import ASSET_REFERENCE_ROLES, ASSET_TYPES, Asset, AssetReferenceImage, AssetVersion
from app.models.image import IMAGE_KINDS, REVIEW_STATUSES, Image
from app.models.job import (
    JOB_ITEM_STATUSES,
    JOB_KINDS,
    JOB_SOURCES,
    JOB_STATUSES,
    STAGE_STATUSES,
    Job,
    JobEvent,
    JobItem,
    JobStage,
    JobStageItem,
)
from app.models.prompt import Prompt, PromptVersion
from app.models.recipe import Recipe, RecipeAssetSnapshot, RecipeVersion
from app.models.system import SystemInfo

__all__ = [
    "ASSET_REFERENCE_ROLES",
    "ASSET_TYPES",
    "Asset",
    "AssetReferenceImage",
    "AssetVersion",
    "IMAGE_KINDS",
    "REVIEW_STATUSES",
    "Image",
    "JOB_ITEM_STATUSES",
    "JOB_KINDS",
    "JOB_SOURCES",
    "JOB_STATUSES",
    "STAGE_STATUSES",
    "Job",
    "JobEvent",
    "JobItem",
    "JobStage",
    "JobStageItem",
    "Prompt",
    "PromptVersion",
    "Recipe",
    "RecipeAssetSnapshot",
    "RecipeVersion",
    "SystemInfo",
]
