"""Recipes API：只做请求解析 → 调用 Service → 返回 Response（规范 §三十三）。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_storage
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.engine.base import EngineError
from app.engine.factory import resolve_workflow_modules
from app.models import Image, Recipe, RecipeVersion
from app.schemas.recipe import (
    RecipeListResponse,
    RecipeMetaUpdateRequest,
    RecipeResponse,
    RecipeSaveRequest,
    RecipeVersionResponse,
    recipe_response,
    recipe_version_response,
)
from app.schemas.workbench import WorkbenchSnapshotModel, WorkflowModuleRefModel
from app.services import image_service, recipe_service
from app.services.prompt_composer import compose_structured
from app.storage.manager import StorageManager

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _pin_workflow_modules(
    settings: Settings, modules: list[WorkflowModuleRefModel]
) -> list[dict]:
    """Task2（Phase 5.1）：保存 Recipe 时尽可能固化模块执行身份（含双指纹）。

    老配方以后不得偷偷使用新版 Workflow：能解析出真实身份就固化（与 Job 创建同一解析器）；
    模块暂不可用（binding 未配置等）时保留原始模块引用，不阻塞保存——
    执行/提交时由 PipelineValidator / Adapter 明确报错，绝不静默降级。
    """
    pinned: list[dict] = []
    for module in modules:
        data = module.model_dump()
        config = data.get("config") if isinstance(data.get("config"), dict) else {}
        try:
            resolved = resolve_workflow_modules(settings, [data])
        except EngineError:
            pinned.append(data)
            continue
        # 解析器只产出执行身份；config 必须原样保留（Task3：模块参数唯一入口）
        pinned.append({**resolved[0], "config": config})
    return pinned


def _snapshot_to_version_args(
    snapshot: WorkbenchSnapshotModel,
    session: Session,
    storage: StorageManager,
    settings: Settings,
) -> dict:
    """WorkbenchSnapshot → RecipeVersion 参数。

    结构化模式下正向 Prompt 由**后端权威合成**（compose_structured），
    不信任前端拼接结果，保证"UI 看到的 == 保存的"（规范 §九）。
    Phase 5 §九：输入图片快照（image_id + file hash + role）在此解析；
    图片记录必须存在（保存时即校验），hash 现算或取导入记录值。
    Phase 5.1 Task2：workflow_modules 保存完整执行身份（provider/双 hash/config 不得丢失）。
    """
    if snapshot.prompt_mode == "structured":
        positive = compose_structured(snapshot.structured_prompt.model_dump())
    else:
        positive = snapshot.full_prompt

    input_images: list[dict] = []
    for ref in snapshot.input_images:
        image = session.get(Image, ref.image_id)
        if image is None:
            raise NotFoundError("输入图片不存在", code="IMAGE_NOT_FOUND")
        input_images.append({
            "role": ref.role,
            "image_id": ref.image_id,
            "sha256": image_service.file_sha256(session, storage, image),
        })

    return dict(
        prompt_mode=snapshot.prompt_mode,
        positive_prompt=positive,
        negative_prompt=snapshot.negative_prompt,
        structured=snapshot.structured_prompt.model_dump(),
        source_prompt_id=snapshot.source_prompt_id,
        source_prompt_version_id=snapshot.source_prompt_version_id,
        generation_settings={
            "model_ref": None,  # Phase 1 固定为空槽位（规范 §二十七）
            "width": snapshot.width,
            "height": snapshot.height,
            "default_count": snapshot.count,
            "seed_mode": snapshot.seed_mode,
            "params": {},
        },
        workflow_modules=_pin_workflow_modules(settings, snapshot.workflow_modules),
        selected_assets={
            slot: {"asset_id": ref.asset_id, "asset_version_id": ref.asset_version_id}
            for slot, ref in snapshot.selected_assets.items()
        },
        input_images=input_images,
    )


def _missing_image_ids(session: Session, version: RecipeVersion) -> set[str]:
    """输入图快照中已不存在的 image_id（§九：必须明确显示"输入图片已丢失"）。"""
    missing: set[str] = set()
    for ref in json.loads(version.input_images_json or "[]"):
        if isinstance(ref, dict) and ref.get("image_id") and session.get(Image, ref["image_id"]) is None:
            missing.add(str(ref["image_id"]))
    return missing


def _version_response(session: Session, version: RecipeVersion) -> RecipeVersionResponse:
    return recipe_version_response(version, _missing_image_ids(session, version))


def _recipe_response(session: Session, recipe: Recipe, current: RecipeVersion | None) -> RecipeResponse:
    return recipe_response(
        recipe, current, _missing_image_ids(session, current) if current is not None else None
    )


@router.get("", response_model=RecipeListResponse, summary="配方列表")
def list_recipes(
    search: str | None = Query(default=None),
    favorite: bool | None = Query(default=None),
    archived: bool | None = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> RecipeListResponse:
    items, total = recipe_service.list_recipes(
        session, search=search, favorite=favorite, archived=archived, limit=limit, offset=offset
    )
    return RecipeListResponse(
        items=[_recipe_response(session, recipe, recipe_service.get_current_version(session, recipe))
               for recipe in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=RecipeResponse, status_code=201, summary="保存配方（+v1，快照当前工作台）")
def create_recipe(
    request: Request,
    body: RecipeSaveRequest,
    session: Session = Depends(get_session),
    storage: StorageManager = Depends(get_storage),
) -> RecipeResponse:
    settings: Settings = request.app.state.settings
    recipe = recipe_service.create_recipe(
        session, name=body.name, favorite=body.favorite,
        **_snapshot_to_version_args(body.snapshot, session, storage, settings),
    )
    return _recipe_response(session, recipe, recipe_service.get_current_version(session, recipe))


@router.get("/{recipe_id}", response_model=RecipeResponse, summary="配方详情")
def get_recipe(recipe_id: str, session: Session = Depends(get_session)) -> RecipeResponse:
    recipe = recipe_service.get_recipe(session, recipe_id)
    return _recipe_response(session, recipe, recipe_service.get_current_version(session, recipe))


@router.patch("/{recipe_id}", response_model=RecipeResponse, summary="修改元数据（不产生内容版本）")
def update_recipe_meta(
    recipe_id: str, request: RecipeMetaUpdateRequest, session: Session = Depends(get_session)
) -> RecipeResponse:
    recipe = recipe_service.update_recipe_meta(session, recipe_id, name=request.name, favorite=request.favorite)
    return _recipe_response(session, recipe, recipe_service.get_current_version(session, recipe))


@router.post("/{recipe_id}/versions", response_model=RecipeVersionResponse, status_code=201, summary="新增配方版本")
def add_recipe_version(
    recipe_id: str,
    request: Request,
    body: RecipeSaveRequest,
    session: Session = Depends(get_session),
    storage: StorageManager = Depends(get_storage),
) -> RecipeVersionResponse:
    settings: Settings = request.app.state.settings
    recipe_service.get_recipe(session, recipe_id)  # 确认存在
    version, _ = recipe_service.add_recipe_version(
        session, recipe_id,
        **_snapshot_to_version_args(body.snapshot, session, storage, settings),
    )
    return _version_response(session, version)


@router.get("/{recipe_id}/versions", response_model=list[RecipeVersionResponse], summary="版本历史")
def list_recipe_versions(recipe_id: str, session: Session = Depends(get_session)) -> list[RecipeVersionResponse]:
    return [_version_response(session, version) for version in recipe_service.list_versions(session, recipe_id)]


@router.post(
    "/{recipe_id}/versions/{version_id}/restore",
    response_model=RecipeVersionResponse,
    status_code=201,
    summary="恢复旧版本（复制为新最新版，含素材快照）",
)
def restore_recipe_version(
    recipe_id: str, version_id: str, session: Session = Depends(get_session)
) -> RecipeVersionResponse:
    version = recipe_service.restore_recipe_version(session, recipe_id, version_id)
    return _version_response(session, version)


@router.post("/{recipe_id}/archive", response_model=RecipeResponse, summary="归档（软删除）")
def archive_recipe(recipe_id: str, session: Session = Depends(get_session)) -> RecipeResponse:
    recipe = recipe_service.set_archived(session, recipe_id, archived=True)
    return _recipe_response(session, recipe, recipe_service.get_current_version(session, recipe))


@router.post("/{recipe_id}/restore", response_model=RecipeResponse, summary="从归档恢复")
def restore_recipe(recipe_id: str, session: Session = Depends(get_session)) -> RecipeResponse:
    recipe = recipe_service.set_archived(session, recipe_id, archived=False)
    return _recipe_response(session, recipe, recipe_service.get_current_version(session, recipe))
