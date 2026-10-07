"""Phase 1 API 层测试：错误格式 / 列表参数 / 上传 / Workbench Snapshot（规范 §三十四-§三十六、§五十二）。"""
from __future__ import annotations

import json


def _png():  # 最小合法 PNG
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d494844520000000100000001080600000"
        "01f15c4890000000d49444154789c6260000000060005"
        "27de3bbb0000000049454e44ae426082"
    )


def test_error_format_is_unified(client):
    """统一错误格式（规范 §三十六）。"""
    response = client.get("/api/v1/prompts/prm_missing")
    assert response.status_code == 404
    body = response.json()
    assert body == {"error": {"code": "PROMPT_NOT_FOUND", "message": "Prompt 不存在"}}

    response = client.post("/api/v1/prompts", json={"mode": "structured"})  # 缺 name → 422
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_prompt_crud_flow(client):
    created = client.post("/api/v1/prompts", json={
        "name": "人像", "mode": "structured",
        "structured": {"style": "anime", "face": "侧脸"},
        "negative_prompt": "blur",
    })
    assert created.status_code == 201
    prompt = created.json()
    assert prompt["current_version"]["version_no"] == 1
    # 结构化保存后 positive_prompt 为后端合成结果
    assert prompt["current_version"]["positive_prompt"] == "anime, 侧脸"

    prompt_id = prompt["id"]
    # PATCH 元数据不建版本
    patched = client.patch(f"/api/v1/prompts/{prompt_id}", json={"favorite": True}).json()
    assert patched["favorite"] is True and patched["current_version"]["version_no"] == 1

    # 新内容版本
    v2 = client.post(f"/api/v1/prompts/{prompt_id}/versions", json={
        "mode": "structured",
        "structured": {"style": "realistic"},
    }).json()
    assert v2["version_no"] == 2

    versions = client.get(f"/api/v1/prompts/{prompt_id}/versions").json()
    assert [v["version_no"] for v in versions] == [2, 1]

    # compose 接口与保存规则一致（规范 §九）
    composed = client.post("/api/v1/prompts/compose", json={
        "mode": "structured", "structured": {"style": "anime", "face": "侧脸"}
    }).json()
    assert composed == {"composed_prompt": "anime, 侧脸"}

    # 归档 → 列表默认不出现 → 恢复
    client.post(f"/api/v1/prompts/{prompt_id}/archive")
    assert client.get("/api/v1/prompts").json()["total"] == 0
    client.post(f"/api/v1/prompts/{prompt_id}/restore")
    assert client.get("/api/v1/prompts").json()["total"] == 1


def test_asset_upload_and_preview(client, png_bytes):
    created = client.post("/api/v1/assets", data={
        "name": "白衬衫", "type": "clothing", "prompt_text": "white shirt",
        "tags": json.dumps(["衬衫", "白"]), "notes": "", "favorite": "false",
    }, files={"preview": ("shirt.png", png_bytes, "image/png")})
    assert created.status_code == 201
    asset = created.json()
    assert asset["type"] == "clothing"
    assert asset["current_version"]["tags"] == ["衬衫", "白"]
    assert asset["current_version"]["preview_path"].startswith("assets/clothing/")

    # 预览图可取回且为 PNG
    preview = client.get(f"/api/v1/assets/{asset['id']}/preview")
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.content[:4] == b"\x89PNG"

    # 列表 + 类型过滤
    listed = client.get("/api/v1/assets", params={"type": "clothing"}).json()
    assert listed["total"] == 1
    assert client.get("/api/v1/assets", params={"type": "face"}).json()["total"] == 0

    # 非法扩展名 → 统一错误
    bad = client.post("/api/v1/assets", data={
        "name": "x", "type": "face",
    }, files={"preview": ("evil.gif", png_bytes, "image/gif")})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    # 内容与扩展名不符
    fake = client.post("/api/v1/assets", data={
        "name": "x", "type": "face",
    }, files={"preview": ("fake.png", b"junk", "image/png")})
    assert fake.json()["error"]["code"] == "INVALID_FILE"


def test_asset_version_and_workbench(client, png_bytes):
    asset = client.post("/api/v1/assets", data={
        "name": "牛仔裤", "type": "clothing", "prompt_text": "denim jeans",
    }, files={"preview": ("a.png", png_bytes, "image/png")}).json()

    # 编辑 → v2
    v2 = client.post(f"/api/v1/assets/{asset['id']}/versions", data={
        "prompt_text": "denim jeans, high waist",
    }, files={"preview": ("b.png", png_bytes, "image/png")})
    assert v2.status_code == 201
    assert v2.json()["version_no"] == 2

    versions = client.get(f"/api/v1/assets/{asset['id']}/versions").json()
    assert [v["version_no"] for v in versions] == [2, 1]
    # v1 预览仍可取（旧版本文件保留）
    assert client.get(f"/api/v1/assets/{asset['id']}/preview", params={"version": 1}).status_code == 200

    workbench = client.get(f"/api/v1/assets/{asset['id']}/workbench").json()
    assert workbench["slot"] == "clothing"
    assert workbench["snapshot"]["structured_prompt"]["clothing"] == "denim jeans, high waist"
    assert workbench["snapshot"]["selected_assets"]["clothing"]["asset_version_id"] == v2.json()["id"]


def test_recipe_save_and_restore_roundtrip(client, png_bytes):
    asset = client.post("/api/v1/assets", data={
        "name": "红裙", "type": "clothing", "prompt_text": "red dress",
    }, files={"preview": ("a.png", png_bytes, "image/png")}).json()
    version_id = asset["current_version"]["id"]

    snapshot = {
        "prompt_mode": "structured",
        "structured_prompt": {"style": "cinematic", "clothing": "red dress", "scene": "alley"},
        "full_prompt": "", "negative_prompt": "lowres",
        "selected_assets": {"clothing": {"asset_id": asset["id"], "asset_version_id": version_id, "name": "红裙"}},
        "width": 768, "height": 1152, "count": 2, "seed_mode": "random", "workflow_modules": [],
    }
    created = client.post("/api/v1/recipes", json={"name": "小巷写真", "snapshot": snapshot})
    assert created.status_code == 201
    recipe = created.json()
    version = recipe["current_version"]
    assert version["positive_prompt_snapshot"] == "cinematic, red dress, alley"  # 后端权威合成
    assert version["generation_settings"]["width"] == 768
    assert version["generation_settings"]["seed_mode"] == "random"
    assert version["default_count"] == 2
    assert version["asset_snapshots"][0]["prompt"] == "red dress"

    recipe_id = recipe["id"]
    # 修改素材 → 保存新配方版本
    snapshot["structured_prompt"]["scene"] = "rooftop"
    v2 = client.post(f"/api/v1/recipes/{recipe_id}/versions", json={"name": "小巷写真", "snapshot": snapshot}).json()
    assert v2["version_no"] == 2

    # 恢复 v1 → v3（快照原样复制）
    restored = client.post(f"/api/v1/recipes/{recipe_id}/versions/{version['id']}/restore")
    assert restored.status_code == 201
    restored_version = restored.json()
    assert restored_version["version_no"] == 3
    assert restored_version["positive_prompt_snapshot"] == "cinematic, red dress, alley"
    assert restored_version["asset_snapshots"][0]["asset_version_id"] == version_id

    # Workbench 恢复所需字段齐全（规范 §五十）
    assert restored_version["structured_prompt"]["scene"] == "alley"
    assert restored_version["workflow_snapshot"] == {"modules": []}
