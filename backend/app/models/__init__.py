"""数据库模型层。

Phase 0：SystemInfo；
Phase 1：Prompt / PromptVersion、Asset / AssetVersion、Recipe / RecipeVersion / RecipeAssetSnapshot。
Job / JobItem / Image 为后续阶段预留（见 docs/DATA_MODEL_V1.md）。
"""
from app.models.asset import ASSET_TYPES, Asset, AssetVersion
from app.models.prompt import Prompt, PromptVersion
from app.models.recipe import Recipe, RecipeAssetSnapshot, RecipeVersion
from app.models.system import SystemInfo

__all__ = [
    "ASSET_TYPES",
    "Asset",
    "AssetVersion",
    "Prompt",
    "PromptVersion",
    "Recipe",
    "RecipeAssetSnapshot",
    "RecipeVersion",
    "SystemInfo",
]
