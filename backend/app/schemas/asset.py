"""Asset 相关出入参。"""
from typing import Literal

from pydantic import BaseModel, Field

from app.models import Asset, AssetVersion
from app.schemas.workbench import SelectedAssetRef, WorkbenchSnapshotModel
import json


AssetType = Literal["face", "clothing", "pose", "scene"]


class AssetCreateRequest(BaseModel):
    name: str
    type: AssetType
    prompt_text: str = ""
    notes: str = ""
    tags: list[str] = Field(default_factory=list)
    favorite: bool = False


class AssetVersionCreateRequest(BaseModel):
    prompt_text: str | None = None
    notes: str | None = None
    tags: list[str] | None = None


class AssetMetaUpdateRequest(BaseModel):
    name: str | None = None
    favorite: bool | None = None


class AssetVersionResponse(BaseModel):
    id: str
    asset_id: str
    version_no: int
    prompt_text: str
    notes: str
    preview_path: str | None
    reference_images: list[str]
    tags: list[str]
    created_at: str


class AssetResponse(BaseModel):
    id: str
    type: str
    name: str
    favorite: bool
    archived: bool
    source_image_id: str | None
    created_at: str
    updated_at: str
    current_version: AssetVersionResponse | None


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    total: int
    limit: int
    offset: int


class AssetWorkbenchResponse(BaseModel):
    """素材 → 生成工作台（规范 §四十三）：把 prompt_text 填入指定 slot。"""

    slot: AssetType
    asset: AssetResponse
    snapshot: WorkbenchSnapshotModel


def asset_version_response(
    version: AssetVersion, reference_image_ids: list[str] | None = None
) -> AssetVersionResponse:
    """reference_images：Phase 5 起来自 asset_reference_images 关系表（role=face_reference）。

    未传 reference_image_ids 时回落到 legacy reference_images_json（历史数据兼容）。
    """
    return AssetVersionResponse(
        id=version.id,
        asset_id=version.asset_id,
        version_no=version.version_no,
        prompt_text=version.prompt_text,
        notes=version.notes,
        preview_path=version.preview_path,
        reference_images=(
            reference_image_ids
            if reference_image_ids is not None
            else json.loads(version.reference_images_json or "[]")
        ),
        tags=json.loads(version.tags_json or "[]"),
        created_at=version.created_at,
    )


def asset_response(
    asset: Asset,
    current_version: AssetVersion | None,
    reference_image_ids: list[str] | None = None,
) -> AssetResponse:
    return AssetResponse(
        id=asset.id,
        type=asset.type,
        name=asset.name,
        favorite=asset.favorite,
        archived=asset.archived,
        source_image_id=asset.source_image_id,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
        current_version=(
            asset_version_response(current_version, reference_image_ids) if current_version else None
        ),
    )
