"""Prompt 封面预览图：属【元数据】（设置/更换/清除绝不产生 PromptVersion）+ 引用保护 + 迁移 0014。"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select, text

from app.models import PromptVersion
from app.services import image_reference_service


def _count_versions(session, prompt_id: str) -> int:
    return session.execute(
        select(func.count()).select_from(PromptVersion).where(PromptVersion.prompt_id == prompt_id)
    ).scalar_one()


def _create_prompt(client) -> dict:
    response = client.post("/api/v1/prompts", json={
        "name": "封面测试", "mode": "full", "positive_prompt": "masterpiece, 1girl",
    })
    assert response.status_code == 201, response.text
    return response.json()


def _import_image(client, png_bytes: bytes, name: str = "cover.png") -> str:
    response = client.post(
        "/api/v1/images/import",
        files=[("files", (name, png_bytes, "image/png"))],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["imported_count"] == 1, body
    return body["imported"][0]["image"]["id"]


def test_set_preview_sets_metadata_without_new_version(client, session, png_bytes):
    image_id = _import_image(client, png_bytes)
    prompt = _create_prompt(client)
    assert prompt["preview_image_id"] is None
    assert _count_versions(session, prompt["id"]) == 1

    resp = client.put(f"/api/v1/prompts/{prompt['id']}/preview-image", json={"image_id": image_id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["preview_image_id"] == image_id
    # 关键：设置封面不创建 PromptVersion
    assert _count_versions(session, prompt["id"]) == 1
    # 详情接口同样回带 preview_image_id
    assert client.get(f"/api/v1/prompts/{prompt['id']}").json()["preview_image_id"] == image_id


def test_replace_and_clear_preview_never_creates_version(client, session, png_bytes):
    img1 = _import_image(client, png_bytes, "a.png")
    img2 = _import_image(client, png_bytes + b"\x01", "b.png")
    prompt = _create_prompt(client)

    client.put(f"/api/v1/prompts/{prompt['id']}/preview-image", json={"image_id": img1})
    assert _count_versions(session, prompt["id"]) == 1

    # 更换封面
    replaced = client.put(f"/api/v1/prompts/{prompt['id']}/preview-image", json={"image_id": img2})
    assert replaced.json()["preview_image_id"] == img2
    assert _count_versions(session, prompt["id"]) == 1  # 更换不建版本

    # 清除封面
    cleared = client.delete(f"/api/v1/prompts/{prompt['id']}/preview-image")
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["preview_image_id"] is None
    assert _count_versions(session, prompt["id"]) == 1  # 清除不建版本


def test_preview_not_found_errors(client):
    prompt = _create_prompt(client)

    # image_id 不存在 → IMAGE_NOT_FOUND
    resp = client.put(f"/api/v1/prompts/{prompt['id']}/preview-image", json={"image_id": "img_missing"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "IMAGE_NOT_FOUND"

    # prompt 不存在 → PROMPT_NOT_FOUND（PUT 与 DELETE 都校验存在性）
    put_missing = client.put("/api/v1/prompts/prm_missing/preview-image", json={"image_id": "img_x"})
    assert put_missing.status_code == 404
    assert put_missing.json()["error"]["code"] == "PROMPT_NOT_FOUND"

    del_missing = client.delete("/api/v1/prompts/prm_missing/preview-image")
    assert del_missing.status_code == 404
    assert del_missing.json()["error"]["code"] == "PROMPT_NOT_FOUND"


def test_prompt_preview_reference_counting(client, session, png_bytes):
    image_id = _import_image(client, png_bytes)
    prompt = _create_prompt(client)

    before = image_reference_service.count_references(session, image_id)
    assert before["references"]["prompt_preview_ids"] == []
    total_before = before["total"]

    # 设置封面 → 该图被引用，total +1
    client.put(f"/api/v1/prompts/{prompt['id']}/preview-image", json={"image_id": image_id})
    refs = image_reference_service.count_references(session, image_id)
    assert refs["references"]["prompt_preview_ids"] == [prompt["id"]]
    assert refs["total"] == total_before + 1

    # 清除封面 → 不再引用，total 回落
    client.delete(f"/api/v1/prompts/{prompt['id']}/preview-image")
    after = image_reference_service.count_references(session, image_id)
    assert after["references"]["prompt_preview_ids"] == []
    assert after["total"] == total_before


def test_migration_0014_adds_preview_column(settings):
    """对全新临时 SQLite 引擎跑迁移：prompts 表存在 preview_image_id 列且 0014 标记 applied。"""
    from app.database.base import init_database, make_engine
    from app.database.migrations import applied_migration_ids

    engine = make_engine(settings.storage.database_path)
    try:
        init_database(engine)
        assert "0014_prompt_preview_image" in applied_migration_ids(engine)
        with engine.connect() as conn:
            columns = {row[1] for row in conn.execute(text("PRAGMA table_info(prompts)"))}
        assert "preview_image_id" in columns
    finally:
        engine.dispose()
