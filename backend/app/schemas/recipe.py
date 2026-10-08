"""Recipe 相关出入参。"""
import json

from pydantic import BaseModel

from app.models import Recipe, RecipeAssetSnapshot, RecipeVersion
from app.schemas.workbench import (
    GenerationSettingsModel,
    StructuredPromptModel,
    WorkflowSnapshotModel,
    WorkbenchSnapshotModel,
    structured_model_from_json,
)


class RecipeSaveRequest(BaseModel):
    """从生成工作台保存 / 更新配方：携带统一 WorkbenchSnapshot（规范 §四十八、§五十二）。"""

    name: str
    favorite: bool = False
    snapshot: WorkbenchSnapshotModel


class RecipeMetaUpdateRequest(BaseModel):
    name: str | None = None
    favorite: bool | None = None


class RecipeAssetSnapshotResponse(BaseModel):
    id: str
    slot: str
    asset_id: str
    asset_version_id: str
    asset_name: str
    prompt: str
    preview_path: str | None


class RecipeInputImageResponse(BaseModel):
    """RecipeVersion 输入图快照（Phase 5 §九）。

    missing=true 表示该 image_id 对应的图库图片已不存在——前端必须明确显示
    "输入图片已丢失"，绝不静默清空。
    """

    role: str
    image_id: str
    sha256: str | None
    missing: bool = False


class RecipeVersionResponse(BaseModel):
    id: str
    recipe_id: str
    version_no: int
    prompt_mode: str
    positive_prompt_snapshot: str
    negative_prompt_snapshot: str
    structured_prompt: StructuredPromptModel
    source_prompt_id: str | None
    source_prompt_version_id: str | None
    generation_settings: GenerationSettingsModel
    workflow_snapshot: WorkflowSnapshotModel
    input_images: list[RecipeInputImageResponse]
    default_count: int
    created_at: str
    asset_snapshots: list[RecipeAssetSnapshotResponse]


class RecipeResponse(BaseModel):
    id: str
    name: str
    favorite: bool
    archived: bool
    created_at: str
    updated_at: str
    current_version: RecipeVersionResponse | None


class RecipeListResponse(BaseModel):
    items: list[RecipeResponse]
    total: int
    limit: int
    offset: int


def recipe_asset_snapshot_response(snapshot: RecipeAssetSnapshot) -> RecipeAssetSnapshotResponse:
    return RecipeAssetSnapshotResponse(
        id=snapshot.id,
        slot=snapshot.slot,
        asset_id=snapshot.asset_id,
        asset_version_id=snapshot.asset_version_id,
        asset_name=snapshot.asset_name_snapshot,
        prompt=snapshot.prompt_snapshot,
        preview_path=snapshot.preview_path_snapshot,
    )


def recipe_version_response(
    version: RecipeVersion, missing_image_ids: set[str] | None = None
) -> RecipeVersionResponse:
    missing = missing_image_ids or set()
    input_images = [
        RecipeInputImageResponse(
            role=str(ref.get("role", "source")),
            image_id=str(ref.get("image_id", "")),
            sha256=ref.get("sha256"),
            missing=str(ref.get("image_id", "")) in missing,
        )
        for ref in json.loads(version.input_images_json or "[]")
        if isinstance(ref, dict) and ref.get("image_id")
    ]
    return RecipeVersionResponse(
        id=version.id,
        recipe_id=version.recipe_id,
        version_no=version.version_no,
        prompt_mode=version.prompt_mode,
        positive_prompt_snapshot=version.positive_prompt_snapshot,
        negative_prompt_snapshot=version.negative_prompt_snapshot,
        structured_prompt=structured_model_from_json(version.structured_prompt_snapshot),
        source_prompt_id=version.source_prompt_id,
        source_prompt_version_id=version.source_prompt_version_id,
        generation_settings=GenerationSettingsModel(**json.loads(version.generation_settings_json)),
        workflow_snapshot=WorkflowSnapshotModel(**json.loads(version.workflow_snapshot_json)),
        input_images=input_images,
        default_count=version.default_count,
        created_at=version.created_at,
        asset_snapshots=[
            recipe_asset_snapshot_response(snapshot) for snapshot in version.asset_snapshots
        ],
    )


def recipe_response(
    recipe: Recipe,
    current_version: RecipeVersion | None,
    missing_image_ids: set[str] | None = None,
) -> RecipeResponse:
    return RecipeResponse(
        id=recipe.id,
        name=recipe.name,
        favorite=recipe.favorite,
        archived=recipe.archived,
        created_at=recipe.created_at,
        updated_at=recipe.updated_at,
        current_version=(
            recipe_version_response(current_version, missing_image_ids) if current_version else None
        ),
    )
