"""Assets API：只做请求解析 → 调用 Service → 返回 Response（规范 §三十三）。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_storage
from app.core.errors import NotFoundError, ValidationError
from app.core.filetypes import MAX_UPLOAD_BYTES, mime_for_suffix
from app.schemas.asset import (
    AssetListResponse,
    AssetMetaUpdateRequest,
    AssetResponse,
    AssetVersionCreateRequest,
    AssetVersionResponse,
    AssetWorkbenchResponse,
    asset_response,
    asset_version_response,
)
from app.schemas.workbench import SelectedAssetRef, StructuredPromptModel, WorkbenchSnapshotModel
from app.services import asset_service
from app.services.asset_service import PreviewUpload
from app.services.prompt_composer import STRUCTURED_FIELDS
from app.storage.manager import StorageManager

router = APIRouter(prefix="/assets", tags=["assets"])


def _read_upload(upload: UploadFile | None) -> PreviewUpload | None:
    """读取上传内容（超限即拒绝）；无文件或空文件返回 None。"""
    if upload is None:
        return None
    data = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        return None
    return PreviewUpload(filename=upload.filename, content_type=upload.content_type, data=data)


def _parse_tags(tags: str | None) -> list[str] | None:
    if tags is None:
        return None
    try:
        parsed = json.loads(tags)
    except ValueError:
        raise ValidationError("tags 必须为 JSON 字符串数组") from None
    if not isinstance(parsed, list):
        raise ValidationError("tags 必须为 JSON 字符串数组")
    return parsed


@router.get("", response_model=AssetListResponse, summary="素材列表")
def list_assets(
    type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    favorite: bool | None = Query(default=None),
    archived: bool | None = Query(default=False),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> AssetListResponse:
    items, total = asset_service.list_assets(
        session, asset_type=type, search=search, favorite=favorite, archived=archived, limit=limit, offset=offset
    )
    return AssetListResponse(
        items=[asset_response(asset, asset_service.get_current_version(session, asset)) for asset in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=AssetResponse, status_code=201, summary="创建素材（+v1，支持预览图上传）")
async def create_asset(
    name: str = Form(...),
    type: str = Form(...),
    prompt_text: str = Form(""),
    notes: str = Form(""),
    tags: str = Form("[]"),
    favorite: bool = Form(False),
    preview: UploadFile | None = File(default=None),
    session: Session = Depends(get_session),
    storage: StorageManager = Depends(get_storage),
) -> AssetResponse:
    tag_list = _parse_tags(tags) or []
    upload = _read_upload(preview)
    asset = asset_service.create_asset(
        session,
        storage,
        asset_type=type,
        name=name,
        prompt_text=prompt_text,
        notes=notes,
        tags=tag_list,
        favorite=favorite,
        preview=upload,
    )
    return asset_response(asset, asset_service.get_current_version(session, asset))


@router.get("/{asset_id}", response_model=AssetResponse, summary="素材详情")
def get_asset(asset_id: str, session: Session = Depends(get_session)) -> AssetResponse:
    asset = asset_service.get_asset(session, asset_id)
    return asset_response(asset, asset_service.get_current_version(session, asset))


@router.patch("/{asset_id}", response_model=AssetResponse, summary="修改元数据（不产生内容版本）")
def update_asset_meta(
    asset_id: str, request: AssetMetaUpdateRequest, session: Session = Depends(get_session)
) -> AssetResponse:
    asset = asset_service.update_asset_meta(session, asset_id, name=request.name, favorite=request.favorite)
    return asset_response(asset, asset_service.get_current_version(session, asset))


@router.post(
    "/{asset_id}/versions",
    response_model=AssetVersionResponse,
    status_code=201,
    summary="新增素材版本（内容变化才创建；支持新预览图）",
)
async def add_asset_version(
    asset_id: str,
    prompt_text: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    preview: UploadFile | None = File(default=None),
    session: Session = Depends(get_session),
    storage: StorageManager = Depends(get_storage),
) -> AssetVersionResponse:
    tag_list = _parse_tags(tags)
    upload = _read_upload(preview)
    version, _ = asset_service.add_asset_version(
        session, storage, asset_id, prompt_text=prompt_text, notes=notes, tags=tag_list, preview=upload
    )
    return asset_version_response(version)


@router.get("/{asset_id}/versions", response_model=list[AssetVersionResponse], summary="版本历史")
def list_asset_versions(asset_id: str, session: Session = Depends(get_session)) -> list[AssetVersionResponse]:
    return [asset_version_response(version) for version in asset_service.list_versions(session, asset_id)]


@router.get("/{asset_id}/preview", summary="预览图（?version= 指定版本，默认当前版本）")
def get_asset_preview(
    asset_id: str,
    version: int | None = Query(default=None),
    session: Session = Depends(get_session),
    storage: StorageManager = Depends(get_storage),
) -> FileResponse:
    asset = asset_service.get_asset(session, asset_id)
    if version is None:
        current = asset_service.get_current_version(session, asset)
        preview_path = current.preview_path if current else None
    else:
        found = next(
            (v for v in asset_service.list_versions(session, asset_id) if v.version_no == version), None
        )
        preview_path = found.preview_path if found else None
    if not preview_path:
        raise NotFoundError("该版本没有预览图", code="ASSET_PREVIEW_NOT_FOUND")
    absolute = storage.absolutize(preview_path)
    suffix = absolute.suffix.lower()
    return FileResponse(absolute, media_type=mime_for_suffix(suffix))


@router.get("/{asset_id}/workbench", response_model=AssetWorkbenchResponse, summary="素材 → 生成工作台快照")
def asset_to_workbench(asset_id: str, session: Session = Depends(get_session)) -> AssetWorkbenchResponse:
    asset = asset_service.get_asset(session, asset_id)
    current = asset_service.get_current_version(session, asset)
    if current is None:
        raise NotFoundError("素材暂无版本", code="ASSET_VERSION_NOT_FOUND")
    # 把素材 prompt 填入对应 slot（规范 §四十三）；其余 slot 保持为空
    structured_data = dict.fromkeys(STRUCTURED_FIELDS, "")
    structured_data[asset.type] = current.prompt_text
    snapshot = WorkbenchSnapshotModel(
        prompt_mode="structured",
        structured_prompt=StructuredPromptModel(**structured_data),
        selected_assets={
            asset.type: SelectedAssetRef(
                asset_id=asset.id, asset_version_id=current.id, name=asset.name
            )
        },
    )
    return AssetWorkbenchResponse(slot=asset.type, asset=asset_response(asset, current), snapshot=snapshot)


@router.post("/{asset_id}/archive", response_model=AssetResponse, summary="归档（软删除）")
def archive_asset(asset_id: str, session: Session = Depends(get_session)) -> AssetResponse:
    asset = asset_service.set_archived(session, asset_id, archived=True)
    return asset_response(asset, asset_service.get_current_version(session, asset))


@router.post("/{asset_id}/restore", response_model=AssetResponse, summary="从归档恢复")
def restore_asset(asset_id: str, session: Session = Depends(get_session)) -> AssetResponse:
    asset = asset_service.set_archived(session, asset_id, archived=False)
    return asset_response(asset, asset_service.get_current_version(session, asset))
