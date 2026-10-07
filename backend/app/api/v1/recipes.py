"""Recipes API：只做请求解析 → 调用 Service → 返回 Response（规范 §三十三）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.recipe import (
    RecipeListResponse,
    RecipeMetaUpdateRequest,
    RecipeResponse,
    RecipeSaveRequest,
    RecipeVersionResponse,
    recipe_response,
    recipe_version_response,
)
from app.schemas.workbench import WorkbenchSnapshotModel
from app.services import recipe_service
from app.services.prompt_composer import compose_structured

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _snapshot_to_version_args(snapshot: WorkbenchSnapshotModel) -> dict:
    """WorkbenchSnapshot → RecipeVersion 参数。

    结构化模式下正向 Prompt 由**后端权威合成**（compose_structured），
    不信任前端拼接结果，保证"UI 看到的 == 保存的"（规范 §九）。
    """
    if snapshot.prompt_mode == "structured":
        positive = compose_structured(snapshot.structured_prompt.model_dump())
    else:
        positive = snapshot.full_prompt

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
        workflow_modules=snapshot.workflow_modules,
        selected_assets={
            slot: {"asset_id": ref.asset_id, "asset_version_id": ref.asset_version_id}
            for slot, ref in snapshot.selected_assets.items()
        },
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
        items=[recipe_response(recipe, recipe_service.get_current_version(session, recipe)) for recipe in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=RecipeResponse, status_code=201, summary="保存配方（+v1，快照当前工作台）")
def create_recipe(request: RecipeSaveRequest, session: Session = Depends(get_session)) -> RecipeResponse:
    recipe = recipe_service.create_recipe(session, name=request.name, favorite=request.favorite,
                                          **_snapshot_to_version_args(request.snapshot))
    return recipe_response(recipe, recipe_service.get_current_version(session, recipe))


@router.get("/{recipe_id}", response_model=RecipeResponse, summary="配方详情")
def get_recipe(recipe_id: str, session: Session = Depends(get_session)) -> RecipeResponse:
    recipe = recipe_service.get_recipe(session, recipe_id)
    return recipe_response(recipe, recipe_service.get_current_version(session, recipe))


@router.patch("/{recipe_id}", response_model=RecipeResponse, summary="修改元数据（不产生内容版本）")
def update_recipe_meta(
    recipe_id: str, request: RecipeMetaUpdateRequest, session: Session = Depends(get_session)
) -> RecipeResponse:
    recipe = recipe_service.update_recipe_meta(session, recipe_id, name=request.name, favorite=request.favorite)
    return recipe_response(recipe, recipe_service.get_current_version(session, recipe))


@router.post("/{recipe_id}/versions", response_model=RecipeVersionResponse, status_code=201, summary="新增配方版本")
def add_recipe_version(
    recipe_id: str, request: RecipeSaveRequest, session: Session = Depends(get_session)
) -> RecipeVersionResponse:
    recipe_service.get_recipe(session, recipe_id)  # 确认存在
    version, _ = recipe_service.add_recipe_version(
        session, recipe_id, **_snapshot_to_version_args(request.snapshot)
    )
    return recipe_version_response(version)


@router.get("/{recipe_id}/versions", response_model=list[RecipeVersionResponse], summary="版本历史")
def list_recipe_versions(recipe_id: str, session: Session = Depends(get_session)) -> list[RecipeVersionResponse]:
    return [recipe_version_response(version) for version in recipe_service.list_versions(session, recipe_id)]


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
    return recipe_version_response(version)


@router.post("/{recipe_id}/archive", response_model=RecipeResponse, summary="归档（软删除）")
def archive_recipe(recipe_id: str, session: Session = Depends(get_session)) -> RecipeResponse:
    recipe = recipe_service.set_archived(session, recipe_id, archived=True)
    return recipe_response(recipe, recipe_service.get_current_version(session, recipe))


@router.post("/{recipe_id}/restore", response_model=RecipeResponse, summary="从归档恢复")
def restore_recipe(recipe_id: str, session: Session = Depends(get_session)) -> RecipeResponse:
    recipe = recipe_service.set_archived(session, recipe_id, archived=False)
    return recipe_response(recipe, recipe_service.get_current_version(session, recipe))
