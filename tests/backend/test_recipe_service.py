"""RecipeService：CRUD / Prompt 快照 / 素材版本快照 / 恢复（Phase 1 规范 §二十一-§二十九）。"""
from __future__ import annotations

import pytest

from app.core.errors import NotFoundError, ValidationError
from app.services import asset_service, prompt_service, recipe_service
from app.services.asset_service import PreviewUpload
from app.storage.manager import StorageManager


@pytest.fixture()
def storage(settings) -> StorageManager:
    return StorageManager(settings)


@pytest.fixture()
def clothing_asset(session, storage, png_bytes):
    return asset_service.create_asset(
        session, storage, asset_type="clothing", name="白衬衫", prompt_text="white shirt", preview=PreviewUpload("a.png", "image/png", png_bytes)
    )


def _selected(asset) -> dict:
    version = asset.versions[0]
    return {"clothing": {"asset_id": asset.id, "asset_version_id": version.id}}


def test_create_recipe_with_snapshots(session, storage, png_bytes, clothing_asset):
    prompt = prompt_service.create_prompt(
        session, name="P", mode="structured", structured={"style": "realistic"}
    )
    recipe = recipe_service.create_recipe(
        session,
        name="咖啡店写真",
        prompt_mode="structured",
        structured={"style": "realistic", "scene": "cafe"},
        negative_prompt="blurry",
        source_prompt_id=prompt.id,
        source_prompt_version_id=prompt.current_version_id,
        generation_settings={"width": 832, "height": 1216, "default_count": 4},
        selected_assets=_selected(clothing_asset),
    )
    assert recipe.id.startswith("rcp_")
    version = recipe_service.get_current_version(session, recipe)
    assert version.id.startswith("rcpv_") and version.version_no == 1
    # 结构化模式：正向快照由后端权威合成（规范 §九）
    assert version.positive_prompt_snapshot == "realistic, cafe"
    assert version.source_prompt_id == prompt.id  # FK 知来源（规范 §二十四）
    assert version.default_count == 4
    assert '"width": 832' in version.generation_settings_json
    assert version.generation_settings_json.count("default_count") == 1
    assert '"modules": []' in version.workflow_snapshot_json.replace(", ", ", ") or '"modules":[]' in version.workflow_snapshot_json.replace(" ", "")

    snapshots = version.asset_snapshots
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.slot == "clothing"
    assert snapshot.asset_version_id == clothing_asset.versions[0].id  # 锁定具体版本（规范 §二十六）
    assert snapshot.prompt_snapshot == "white shirt"
    assert snapshot.asset_name_snapshot == "白衬衫"
    assert snapshot.preview_path_snapshot is not None


def test_asset_upgrade_does_not_change_old_recipe(session, storage, png_bytes, clothing_asset):
    """老素材升级后，老 Recipe 仍引用当时的版本（规范 §二十六）。"""
    recipe = recipe_service.create_recipe(
        session, name="R", prompt_mode="full", positive_prompt="x",
        selected_assets=_selected(clothing_asset),
    )
    old_version_id = recipe_service.get_current_version(session, recipe).asset_snapshots[0].asset_version_id

    asset_service.add_asset_version(session, storage, clothing_asset.id, prompt_text="v2 prompt")

    current = recipe_service.get_current_version(session, recipe)
    assert current.asset_snapshots[0].asset_version_id == old_version_id
    assert current.asset_snapshots[0].prompt_snapshot == "white shirt"  # 历史快照不变
    # 且 FK 指向的旧版本内容仍在（未物理修改）
    from app.models import AssetVersion
    assert session.get(AssetVersion, old_version_id).prompt_text == "white shirt"


def test_recipe_restore_copies_snapshots(session, storage, png_bytes, clothing_asset):
    recipe = recipe_service.create_recipe(
        session, name="R", prompt_mode="full", positive_prompt="v1",
        generation_settings={"width": 512, "height": 512},
        selected_assets=_selected(clothing_asset),
    )
    v1 = recipe_service.get_current_version(session, recipe)
    recipe_service.add_recipe_version(
        session, recipe.id, prompt_mode="full", positive_prompt="v2",
        generation_settings={"width": 1024, "height": 1024},
    )

    restored = recipe_service.restore_recipe_version(session, recipe.id, v1.id)
    assert restored.version_no == 3
    assert restored.positive_prompt_snapshot == "v1"
    assert restored.generation_settings_json == v1.generation_settings_json
    assert [s.asset_version_id for s in restored.asset_snapshots] == [v1.asset_snapshots[0].asset_version_id]


def test_recipe_content_change_creates_version_unchanged_skips(session, clothing_asset):
    recipe = recipe_service.create_recipe(
        session, name="R", prompt_mode="full", positive_prompt="v1",
        selected_assets=_selected(clothing_asset),
    )
    version2, created = recipe_service.add_recipe_version(
        session, recipe.id, prompt_mode="full", positive_prompt="v2",
        selected_assets=_selected(clothing_asset),
    )
    assert created and version2.version_no == 2
    current, created_again = recipe_service.add_recipe_version(
        session, recipe.id, prompt_mode="full", positive_prompt="v2",
        selected_assets=_selected(clothing_asset),
    )
    assert not created_again and current.version_no == 2


def test_generation_settings_validation(session):
    with pytest.raises(ValidationError) as exc:
        recipe_service.create_recipe(
            session, name="R", prompt_mode="full", positive_prompt="x",
            generation_settings={"seed_mode": "fixed"},
        )
    assert exc.value.code == "SEED_MODE_INVALID"  # Phase 1 固定 random（规范 §二十九）

    with pytest.raises(ValidationError):
        recipe_service.create_recipe(
            session, name="R", prompt_mode="full", positive_prompt="x",
            generation_settings={"width": 0},
        )


def test_slot_validation_and_duplicate(session, clothing_asset):
    with pytest.raises(ValidationError) as exc:
        recipe_service.create_recipe(
            session, name="R", prompt_mode="full", positive_prompt="x",
            selected_assets={"background": {"asset_id": clothing_asset.id, "asset_version_id": clothing_asset.versions[0].id}},
        )
    assert exc.value.code == "SLOT_INVALID"

    ref = {"asset_id": clothing_asset.id, "asset_version_id": clothing_asset.versions[0].id}
    with pytest.raises(ValidationError) as exc:
        recipe_service.create_recipe(
            session, name="R", prompt_mode="full", positive_prompt="x",
            selected_assets={"clothing": ref, "其他": ref},
        )
    assert exc.value.code == "SLOT_INVALID"  # "其他" 非法 slot 先被拒绝


def test_missing_asset_version_rejected(session):
    with pytest.raises(NotFoundError):
        recipe_service.create_recipe(
            session, name="R", prompt_mode="full", positive_prompt="x",
            selected_assets={"face": {"asset_id": "ast_x", "asset_version_id": "astv_missing"}},
        )


def test_list_and_archive(session):
    r1 = recipe_service.create_recipe(session, name="日常", prompt_mode="full", positive_prompt="x")
    r2 = recipe_service.create_recipe(session, name="夜景", prompt_mode="full", positive_prompt="night", favorite=True)
    recipe_service.set_archived(session, r2.id, archived=True)

    items, total = recipe_service.list_recipes(session)
    assert total == 1 and items[0].id == r1.id
    _, total = recipe_service.list_recipes(session, archived=None)
    assert total == 2
    items, _ = recipe_service.list_recipes(session, favorite=True, archived=None)
    assert [r.id for r in items] == [r2.id]
