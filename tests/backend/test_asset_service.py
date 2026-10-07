"""AssetService：CRUD / 四类型 / 版本不可变 / 文件安全（Phase 1 规范 §十二-§二十）。"""
from __future__ import annotations

import pytest

from app.core.errors import FileValidationError, ValidationError
from app.services import asset_service
from app.services.asset_service import PreviewUpload


def _upload(png_bytes: bytes, name="a.png", mime="image/png") -> PreviewUpload:
    return PreviewUpload(filename=name, content_type=mime, data=png_bytes)


def test_create_asset_four_types(session, settings, png_bytes):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    for i, asset_type in enumerate(("face", "clothing", "pose", "scene")):
        asset = asset_service.create_asset(
            session, storage, asset_type=asset_type, name=f"素材{i}", prompt_text=f"{asset_type} prompt",
            tags=["测试", " x ", "测试"], preview=_upload(png_bytes),
        )
        assert asset.id.startswith("ast_")
        version = asset_service.get_current_version(session, asset)
        assert version.id.startswith("astv_") and version.version_no == 1
        assert version.prompt_text == f"{asset_type} prompt"
        # 文件位于 DataRoot 且相对路径入库（规范 §十七）
        assert version.preview_path.startswith(f"assets/{asset_type}/{asset.id}/v0001/preview")
        assert not version.preview_path.startswith("D:") and ":" not in version.preview_path
        assert storage.absolutize(version.preview_path).is_file()
        # tags 归一化（去空白、去重）
        assert version.tags_json == '["测试", "x"]'


def test_invalid_type_rejected(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    with pytest.raises(ValidationError) as exc:
        asset_service.create_asset(session, storage, asset_type="background", name="x")
    assert exc.value.code == "ASSET_TYPE_INVALID"


def test_version_immutable_and_old_file_kept(session, settings, png_bytes):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    asset = asset_service.create_asset(
        session, storage, asset_type="clothing", name="衫", prompt_text="v1 prompt", preview=_upload(png_bytes)
    )
    v1_path = asset_service.get_current_version(session, asset).preview_path

    # 修改 prompt + 换图 → v2
    version2, created = asset_service.add_asset_version(
        session, storage, asset.id, prompt_text="v2 prompt", preview=_upload(png_bytes, name="b.png")
    )
    assert created and version2.version_no == 2
    assert asset_service.get_current_version(session, asset).id == version2.id
    assert storage.absolutize(v1_path).is_file(), "旧版本文件必须保留（规范 §十五）"
    assert version2.preview_path != v1_path

    # 只改 prompt → v3 且复制旧预览图
    version3, created3 = asset_service.add_asset_version(session, storage, asset.id, prompt_text="v3 prompt")
    assert created3 and version3.version_no == 3
    assert version3.preview_path is not None
    assert storage.absolutize(version3.preview_path).is_file()

    # 内容不变 → 不建新版本
    current, created4 = asset_service.add_asset_version(session, storage, asset.id, prompt_text="v3 prompt")
    assert not created4 and current.version_no == 3


def test_upload_rejects_bad_extension(session, settings, png_bytes):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    with pytest.raises(FileValidationError) as exc:
        asset_service.create_asset(
            session, storage, asset_type="face", name="x",
            preview=PreviewUpload(filename="evil.gif", content_type=None, data=png_bytes),
        )
    assert exc.value.code == "UNSUPPORTED_FILE_TYPE"


def test_upload_rejects_content_mismatch(session, settings, png_bytes):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    with pytest.raises(FileValidationError) as exc:
        asset_service.create_asset(
            session, storage, asset_type="face", name="x",
            preview=PreviewUpload(filename="fake.png", content_type="image/png", data=b"not a png at all"),
        )
    assert exc.value.code == "INVALID_FILE"


def test_upload_rejects_oversize(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    with pytest.raises(FileValidationError) as exc:
        asset_service.create_asset(
            session, storage, asset_type="face", name="x",
            preview=PreviewUpload(filename="big.png", content_type="image/png", data=b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024)),
        )
    assert exc.value.code == "FILE_TOO_LARGE"


def test_db_failure_leaves_no_orphan_file(session, settings, png_bytes, monkeypatch):
    """数据库失败时不得留下无法追踪的正式素材文件（规范 §十九）。"""
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)

    original_commit = session.commit
    def broken_commit():
        original_commit()
        raise RuntimeError("模拟提交失败")

    monkeypatch.setattr(session, "commit", broken_commit)
    with pytest.raises(RuntimeError):
        asset_service.create_asset(
            session, storage, asset_type="clothing", name="x", preview=_upload(png_bytes)
        )
    monkeypatch.undo()

    files = list((settings.storage.data_root / "assets").rglob("*"))
    files = [path for path in files if path.is_file()]
    assert files == [], f"提交失败后不应残留正式素材文件: {files}"
    # 临时目录也不应残留
    temps = [path for path in (settings.storage.data_root / "images" / "temp").iterdir() if path.is_file()]
    assert temps == []


def test_resolve_under_blocks_traversal(settings):
    """路径穿越防护（规范 §十八）。"""
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    ok = storage.resolve_under("assets", "clothing", "ast_x", "v0001", "preview.png")
    assert ok == settings.storage.data_root / "assets" / "clothing" / "ast_x" / "v0001" / "preview.png"

    for evil in ("..", "../escape", "a/b", "a\\b", "C:/windows", "", "/abs"):
        with pytest.raises(ValidationError):
            storage.resolve_under("assets", evil)
    with pytest.raises(ValidationError):
        storage.absolutize("../../outside.png")
