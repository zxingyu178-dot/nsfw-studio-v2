"""Phase 0.12：GET /api/v1/system/status 只读系统状态摘要测试。"""
from __future__ import annotations

import io

from PIL import Image as PILImage


def _png(seed: int) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (32, 32), (seed * 41 % 256, seed * 17 % 256, seed * 7 % 256)).save(
        buffer, format="PNG"
    )
    return buffer.getvalue()


def _import_n(client, n: int) -> None:
    from app.services import image_service
    from app.storage.manager import StorageManager

    storage = StorageManager(client.app.state.settings)
    with client.app.state.session_factory() as session:
        for i in range(n):
            image_service.import_images_batch(
                session, storage, [(f"sys{i}.png", "image/png", _png(i + 1))]
            )


def test_system_status_contract(client):
    _import_n(client, 2)
    resp = client.get("/api/v1/system/status")
    assert resp.status_code == 200
    body = resp.json()

    # 字段齐全
    expected_keys = {
        "app_version", "data_root", "database_path", "database_size",
        "disk_total", "disk_free", "image_count", "thumbnail_count",
        "preview_count", "latest_migration", "engine_runtime",
    }
    assert expected_keys == set(body.keys())

    # 版本 / 路径
    assert body["app_version"] == client.app.state.settings.app.version
    assert body["data_root"] == str(client.app.state.settings.storage.data_root)
    assert body["database_path"].endswith("studio.db")

    # 数值合理
    assert body["database_size"] >= 0
    assert body["disk_total"] > body["disk_free"] > 0
    assert body["image_count"] == 2
    assert 0 <= body["thumbnail_count"] <= body["image_count"]
    assert 0 <= body["preview_count"] <= body["image_count"]

    # 最新迁移（本基线最新 = 0017）
    assert body["latest_migration"] == "0017_image_review_semantics"

    # engine_runtime 是现有状态摘要（含 state）
    assert isinstance(body["engine_runtime"], dict)
    assert "state" in body["engine_runtime"]


def test_system_status_leaks_no_secrets(client):
    resp = client.get("/api/v1/system/status")
    assert resp.status_code == 200
    body = resp.json()
    for banned in ("password", "secret", "token", "python_exe", "working_dir"):
        # 敏感配置键名不得作为顶层字段泄露（engine_name=comfyui 属正常运行时摘要）
        assert banned not in body
