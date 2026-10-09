"""RecipeService（Phase 1 规范 §二十一-§二十九、§三十二、§五十五-§五十七）。

- Recipe = 完整工作台配置快照；Prompt 快照 + 来源 FK 同时保存（§二十四）；
- 素材快照锁定具体 asset_version_id + 当时的 prompt/preview 快照（§二十五、§二十六）；
- 一个 RecipeVersion 一个 slot 最多一个素材（UNIQUE 约束 + Service 校验）；
- seed_mode 固定 random（§二十九；Phase 6 Task3）：Recipe 产品规则不保存固定 Seed，
  "使用此图 Seed"的工作台保存时归一化为 random（不报错，也不强制改 Workbench 状态）；
  generation_settings.model_ref 只是占位槽位，禁止出现具体模型名（§二十七）；
  workflow_snapshot 第一版 {"modules": []}（§二十八）。
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.ids import RECIPE, RECIPE_VERSION, new_id
from app.models import ASSET_TYPES, Asset, AssetVersion, Recipe, RecipeAssetSnapshot, RecipeVersion
from app.services.prompt_composer import compose_structured, dumps_structured

RECIPE_PROMPT_MODES = ("structured", "full")


def get_recipe(session: Session, recipe_id: str) -> Recipe:
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise NotFoundError("配方不存在", code="RECIPE_NOT_FOUND")
    return recipe


def get_current_version(session: Session, recipe: Recipe) -> RecipeVersion | None:
    if recipe.current_version_id is None:
        return None
    return session.get(RecipeVersion, recipe.current_version_id)


def _validate_generation_settings(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """归一化 generation_settings；model_ref 仅允许为 None 或非空字符串占位（不绑定具体模型）。"""
    raw = raw or {}
    model_ref = raw.get("model_ref")
    if model_ref is not None and not isinstance(model_ref, str):
        raise ValidationError("model_ref 必须为 null 或字符串", code="GENERATION_SETTINGS_INVALID")
    try:
        width = int(raw.get("width", 1024))
        height = int(raw.get("height", 1024))
        default_count = int(raw.get("default_count", 1))
    except (TypeError, ValueError):
        raise ValidationError("width / height / default_count 必须为整数", code="GENERATION_SETTINGS_INVALID") from None
    if width <= 0 or height <= 0:
        raise ValidationError("尺寸必须为正整数", code="GENERATION_SETTINGS_INVALID")
    if default_count < 1 or default_count > 64:
        raise ValidationError("数量取值范围为 1-64", code="GENERATION_SETTINGS_INVALID")
    seed_mode = str(raw.get("seed_mode", "random"))
    if seed_mode not in ("random", "fixed"):
        raise ValidationError("seed_mode 必须为 random 或 fixed", code="SEED_MODE_INVALID")
    # Phase 6 Task7：生成模式随 Recipe 版本往返（旧版本无该字段 → None → 前端按输入图推断）
    generation_mode = raw.get("generation_mode")
    if generation_mode not in (None, "text", "image"):
        raise ValidationError("generation_mode 必须为 text / image", code="GENERATION_SETTINGS_INVALID")
    params = raw.get("params", {})
    if not isinstance(params, dict):
        raise ValidationError("params 必须为对象", code="GENERATION_SETTINGS_INVALID")
    return {
        "model_ref": model_ref,
        "width": width,
        "height": height,
        "default_count": default_count,
        # Phase 6 Task3：固定 Seed 归一化为 random / seed=null——
        # "使用此图 Seed"的工作台可以直接保存 Recipe（201），重新打开后是 random。
        "seed_mode": "random",
        "generation_mode": generation_mode,
        "params": params,
    }


def _validate_workflow_snapshot(modules: list[dict] | None) -> dict[str, Any]:
    """归一化 workflow_snapshot（Phase 5.1 Task1/Task2）：保留**完整执行身份**。

    每个模块必须包含（缺失字段留 None，但结构固定）：
        module_id / module_version / provider / binding_version
        workflow_hash / binding_hash / config
    **禁止静默丢弃身份**——否则旧 Recipe 可能偷偷使用新版 Workflow，破坏可复现性；
    历史 Job → 打开工作台 → 保存 Recipe → 关闭 → 重新打开，身份必须完全一致。
    """
    if modules is None:
        return {"modules": []}
    if not isinstance(modules, list):
        raise ValidationError("workflow modules 必须为数组", code="WORKFLOW_SNAPSHOT_INVALID")
    cleaned = []
    for module in modules:
        data = module.model_dump() if isinstance(module, BaseModel) else module
        if not isinstance(data, dict) or not isinstance(data.get("module_id"), str):
            raise ValidationError("workflow module 缺少 module_id", code="WORKFLOW_SNAPSHOT_INVALID")
        config = data.get("config")
        module_version = data.get("module_version")
        cleaned.append(
            {
                "module_id": data["module_id"],
                "module_version": str(module_version) if module_version else None,
                "provider": data.get("provider"),
                "binding_version": data.get("binding_version"),
                "workflow_hash": data.get("workflow_hash"),
                "binding_hash": data.get("binding_hash"),
                "config": config if isinstance(config, dict) else {},
            }
        )
    return {"modules": cleaned}


RECIPE_INPUT_ROLES = ("source",)


def _validate_input_images(refs: list[dict] | None) -> list[dict[str, Any]]:
    """归一化输入图快照（Phase 5 §九）：至少保存 image_id + file hash + role。

    第一版最多 1 张（role=source）；sha256 由 API 层在保存时解析（文件缺失可为 None，
    但字段必须存在——历史版本据此判断"输入图片已丢失"而不是静默清空）。
    """
    if refs is None:
        return []
    if not isinstance(refs, list):
        raise ValidationError("input_images 必须为数组", code="RECIPE_INPUT_INVALID")
    if len(refs) > 1:
        raise ValidationError("Phase 5 输入图片最多 1 张", code="RECIPE_INPUT_INVALID")
    cleaned: list[dict[str, Any]] = []
    for ref in refs:
        if not isinstance(ref, dict) or not ref.get("image_id"):
            raise ValidationError("input_images 结构非法", code="RECIPE_INPUT_INVALID")
        role = ref.get("role", "source")
        if role not in RECIPE_INPUT_ROLES:
            raise ValidationError(f"非法输入图角色: {role}", code="RECIPE_INPUT_INVALID")
        sha256 = ref.get("sha256")
        if sha256 is not None and not isinstance(sha256, str):
            raise ValidationError("sha256 必须为字符串或 null", code="RECIPE_INPUT_INVALID")
        cleaned.append({"role": role, "image_id": str(ref["image_id"]), "sha256": sha256})
    return cleaned


def _validate_prompt_mode(mode: str) -> str:
    if mode not in RECIPE_PROMPT_MODES:
        raise ValidationError(f"非法 Prompt 模式: {mode}", code="PROMPT_MODE_INVALID")
    return mode


def _build_asset_snapshots(
    session: Session,
    recipe_version_id: str,
    selected_assets: Mapping[str, Mapping[str, str]] | None,
) -> list[RecipeAssetSnapshot]:
    """按 slot 锁定 asset_version，并复制当时的名称/prompt/preview 快照。"""
    snapshots: list[RecipeAssetSnapshot] = []
    if not selected_assets:
        return snapshots
    seen_slots: set[str] = set()
    for slot, ref in selected_assets.items():
        if slot not in ASSET_TYPES:
            raise ValidationError(f"非法素材槽位: {slot}", code="SLOT_INVALID")
        if slot in seen_slots:
            raise ValidationError(f"槽位重复: {slot}", code="SLOT_DUPLICATED")
        seen_slots.add(slot)

        asset_version = session.get(AssetVersion, str(ref.get("asset_version_id", "")))
        if asset_version is None:
            raise NotFoundError(f"素材版本不存在: {ref.get('asset_version_id')}", code="ASSET_VERSION_NOT_FOUND")
        if ref.get("asset_id") and asset_version.asset_id != ref["asset_id"]:
            raise ValidationError("asset_version 与 asset_id 不匹配", code="ASSET_MISMATCH")

        snapshot = RecipeAssetSnapshot(
            id=new_id("rcpas"),
            recipe_version_id=recipe_version_id,
            slot=slot,
            asset_id=asset_version.asset_id,
            asset_version_id=asset_version.id,
            asset_name_snapshot="",  # 下面补齐
            prompt_snapshot=asset_version.prompt_text,
            preview_path_snapshot=asset_version.preview_path,
        )
        asset = session.get(Asset, asset_version.asset_id)
        snapshot.asset_name_snapshot = asset.name if asset else ""
        snapshots.append(snapshot)
    return snapshots


def _authoritative_positive(prompt_mode: str, positive_prompt: str, structured: dict | None) -> str:
    """结构化模式：正向快照由后端权威合成（幂等）；完整模式：使用传入全文。"""
    if prompt_mode == "structured":
        return positive_prompt or compose_structured(structured)
    return positive_prompt or ""


def create_recipe(
    session: Session,
    *,
    name: str,
    prompt_mode: str,
    positive_prompt: str = "",
    negative_prompt: str = "",
    structured: dict | None = None,
    source_prompt_id: str | None = None,
    source_prompt_version_id: str | None = None,
    generation_settings: Mapping[str, Any] | None = None,
    workflow_modules: list[dict] | None = None,
    selected_assets: Mapping[str, Mapping[str, str]] | None = None,
    input_images: list[dict] | None = None,
    favorite: bool = False,
) -> Recipe:
    """创建 Recipe + RecipeVersion + AssetSnapshots（单事务）。"""
    if not name or not name.strip():
        raise ValidationError("配方名称不能为空")
    _validate_prompt_mode(prompt_mode)
    settings = _validate_generation_settings(generation_settings)
    workflow_snapshot = _validate_workflow_snapshot(workflow_modules)
    input_image_refs = _validate_input_images(input_images)

    recipe = Recipe(id=new_id(RECIPE), name=name.strip(), favorite=favorite, archived=False)
    version = RecipeVersion(
        id=new_id(RECIPE_VERSION),
        recipe_id=recipe.id,
        version_no=1,
        prompt_mode=prompt_mode,
        positive_prompt_snapshot=_authoritative_positive(prompt_mode, positive_prompt, structured),
        negative_prompt_snapshot=negative_prompt or "",
        structured_prompt_snapshot=dumps_structured(structured),
        source_prompt_id=source_prompt_id,
        source_prompt_version_id=source_prompt_version_id,
        generation_settings_json=json.dumps(settings, ensure_ascii=False),
        workflow_snapshot_json=json.dumps(workflow_snapshot, ensure_ascii=False),
        input_images_json=json.dumps(input_image_refs, ensure_ascii=False),
        default_count=settings["default_count"],
    )
    recipe.current_version_id = version.id
    try:
        session.add(recipe)
        session.add(version)
        session.flush()  # 让 version.id 可用于快照外键
        for snapshot in _build_asset_snapshots(session, version.id, selected_assets):
            session.add(snapshot)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ConflictError("版本号冲突，请重试", code="VERSION_CONFLICT")
    except Exception:
        session.rollback()
        raise
    return recipe


def add_recipe_version(
    session: Session,
    recipe_id: str,
    *,
    prompt_mode: str,
    positive_prompt: str = "",
    negative_prompt: str = "",
    structured: dict | None = None,
    source_prompt_id: str | None = None,
    source_prompt_version_id: str | None = None,
    generation_settings: Mapping[str, Any] | None = None,
    workflow_modules: list[dict] | None = None,
    selected_assets: Mapping[str, Mapping[str, str]] | None = None,
    input_images: list[dict] | None = None,
) -> tuple[RecipeVersion, bool]:
    """工作台配置任何变化 → 新 RecipeVersion；与当前版本一致 → 不建新版本。"""
    recipe = get_recipe(session, recipe_id)
    _validate_prompt_mode(prompt_mode)
    settings = _validate_generation_settings(generation_settings)
    workflow_snapshot = _validate_workflow_snapshot(workflow_modules)
    input_image_refs = _validate_input_images(input_images)

    current = get_current_version(session, recipe)
    structured_json = dumps_structured(structured)
    authoritative_positive = _authoritative_positive(prompt_mode, positive_prompt, structured)
    if current is not None and (
        current.prompt_mode == prompt_mode
        and current.positive_prompt_snapshot == authoritative_positive
        and current.negative_prompt_snapshot == (negative_prompt or "")
        and current.structured_prompt_snapshot == structured_json
        and current.generation_settings_json == json.dumps(settings, ensure_ascii=False)
        and current.workflow_snapshot_json == json.dumps(workflow_snapshot, ensure_ascii=False)
        and (current.input_images_json or "[]") == json.dumps(input_image_refs, ensure_ascii=False)
        and current.default_count == settings["default_count"]
        and _snapshots_signature(session, current) == _selected_signature(selected_assets)
    ):
        return current, False

    version = RecipeVersion(
        id=new_id(RECIPE_VERSION),
        recipe_id=recipe.id,
        version_no=_next_version_no(session, recipe.id),
        prompt_mode=prompt_mode,
        positive_prompt_snapshot=authoritative_positive,
        negative_prompt_snapshot=negative_prompt or "",
        structured_prompt_snapshot=structured_json,
        source_prompt_id=source_prompt_id,
        source_prompt_version_id=source_prompt_version_id,
        generation_settings_json=json.dumps(settings, ensure_ascii=False),
        workflow_snapshot_json=json.dumps(workflow_snapshot, ensure_ascii=False),
        input_images_json=json.dumps(input_image_refs, ensure_ascii=False),
        default_count=settings["default_count"],
    )
    recipe.current_version_id = version.id
    try:
        session.add(version)
        session.flush()
        for snapshot in _build_asset_snapshots(session, version.id, selected_assets):
            session.add(snapshot)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ConflictError("版本号冲突，请重试", code="VERSION_CONFLICT")
    except Exception:
        session.rollback()
        raise
    return version, True


def _snapshots_signature(session: Session, version: RecipeVersion) -> dict[str, str]:
    return {
        snapshot.slot: snapshot.asset_version_id
        for snapshot in session.execute(
            select(RecipeAssetSnapshot).where(RecipeAssetSnapshot.recipe_version_id == version.id)
        ).scalars()
    }


def _selected_signature(selected_assets: Mapping[str, Mapping[str, str]] | None) -> dict[str, str]:
    if not selected_assets:
        return {}
    return {slot: str(ref.get("asset_version_id", "")) for slot, ref in selected_assets.items()}


def restore_recipe_version(session: Session, recipe_id: str, version_id: str) -> RecipeVersion:
    """恢复旧版本：复制其全部内容（含素材快照锁定关系）创建新的最新版。"""
    recipe = get_recipe(session, recipe_id)
    old = session.get(RecipeVersion, version_id)
    if old is None or old.recipe_id != recipe.id:
        raise NotFoundError("配方版本不存在", code="RECIPE_VERSION_NOT_FOUND")

    version = RecipeVersion(
        id=new_id(RECIPE_VERSION),
        recipe_id=recipe.id,
        version_no=_next_version_no(session, recipe.id),
        prompt_mode=old.prompt_mode,
        positive_prompt_snapshot=old.positive_prompt_snapshot,
        negative_prompt_snapshot=old.negative_prompt_snapshot,
        structured_prompt_snapshot=old.structured_prompt_snapshot,
        source_prompt_id=old.source_prompt_id,
        source_prompt_version_id=old.source_prompt_version_id,
        generation_settings_json=old.generation_settings_json,
        workflow_snapshot_json=old.workflow_snapshot_json,
        # §九：输入图快照原样保留（图片已丢失时仍保留引用，由响应标记"已丢失"，绝不静默清空）
        input_images_json=old.input_images_json or "[]",
        default_count=old.default_count,
    )
    recipe.current_version_id = version.id
    try:
        session.add(version)
        session.flush()
        for old_snapshot in old.asset_snapshots:
            session.add(
                RecipeAssetSnapshot(
                    id=new_id("rcpas"),
                    recipe_version_id=version.id,
                    slot=old_snapshot.slot,
                    asset_id=old_snapshot.asset_id,
                    asset_version_id=old_snapshot.asset_version_id,
                    asset_name_snapshot=old_snapshot.asset_name_snapshot,
                    prompt_snapshot=old_snapshot.prompt_snapshot,
                    preview_path_snapshot=old_snapshot.preview_path_snapshot,
                )
            )
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ConflictError("版本号冲突，请重试", code="VERSION_CONFLICT")
    except Exception:
        session.rollback()
        raise
    return version


def update_recipe_meta(
    session: Session,
    recipe_id: str,
    *,
    name: str | None = None,
    favorite: bool | None = None,
) -> Recipe:
    recipe = get_recipe(session, recipe_id)
    if name is not None:
        if not name.strip():
            raise ValidationError("配方名称不能为空")
        recipe.name = name.strip()
    if favorite is not None:
        recipe.favorite = favorite
    session.commit()
    return recipe


def _next_version_no(session: Session, recipe_id: str) -> int:
    current_max = session.execute(
        select(func.max(RecipeVersion.version_no)).where(RecipeVersion.recipe_id == recipe_id)
    ).scalar_one()
    return (current_max or 0) + 1


def get_version(session: Session, recipe_id: str, version_id: str) -> RecipeVersion:
    version = session.get(RecipeVersion, version_id)
    if version is None or version.recipe_id != recipe_id:
        raise NotFoundError("配方版本不存在", code="RECIPE_VERSION_NOT_FOUND")
    return version


def list_versions(session: Session, recipe_id: str) -> list[RecipeVersion]:
    recipe = get_recipe(session, recipe_id)
    return list(
        session.execute(
            select(RecipeVersion)
            .where(RecipeVersion.recipe_id == recipe.id)
            .order_by(RecipeVersion.version_no.desc())
        ).scalars()
    )


def list_recipes(
    session: Session,
    *,
    search: str | None = None,
    favorite: bool | None = None,
    archived: bool | None = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Recipe], int]:
    if limit < 1 or limit > 200:
        raise ValidationError("limit 取值范围为 1-200")
    if offset < 0:
        raise ValidationError("offset 不能为负")

    query = select(Recipe)
    if archived is not None:
        query = query.where(Recipe.archived == archived)
    if favorite is not None:
        query = query.where(Recipe.favorite == favorite)
    if search:
        like = f"%{search.strip()}%"
        matching_versions = select(RecipeVersion.recipe_id).where(
            RecipeVersion.positive_prompt_snapshot.like(like)
        )
        query = query.where(or_(Recipe.name.like(like), Recipe.id.in_(matching_versions)))

    total = session.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    items = list(
        session.execute(query.order_by(Recipe.updated_at.desc()).limit(limit).offset(offset)).scalars()
    )
    return items, int(total)


def set_archived(session: Session, recipe_id: str, archived: bool) -> Recipe:
    recipe = get_recipe(session, recipe_id)
    recipe.archived = archived
    session.commit()
    return recipe
