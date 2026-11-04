"""upscale 模块下线验收（产品层）：注册表 / 旧路由 / 历史 kind 读取。"""
from __future__ import annotations

from app.services import image_service
from app.storage.manager import StorageManager
from app.workflows.registry import default_registry


def test_default_registry_contains_exactly_four_modules():
    ids = default_registry().ids()
    assert ids == ["anime_generate", "basic_generate", "img2img", "reference_generate"]
    assert default_registry().has("upscale", "v1") is False


def test_upscale_api_endpoint_is_gone(client):
    response = client.post("/api/v1/images/upscale", json={"image_ids": ["img_missing"]})
    assert response.status_code in (404, 405), response.text


def test_historical_upscaled_images_remain_queryable_and_readable(client, session, png_bytes):
    """历史 kind='upscaled' 的图片查询 / 读取 / 父子关系必须继续可用。"""
    with session:
        storage = StorageManager(client.app.state.settings)
        image = image_service.import_engine_output(
            session, storage, data=png_bytes, original_filename="legacy_upscaled.png",
            source="import", kind="upscaled",
        )
        image_id = image.id
        session.commit()

    listing = client.get("/api/v1/images", params={"kind": "upscaled"}).json()
    item = next(item for item in listing["items"] if item["id"] == image_id)
    assert item["kind"] == "upscaled"
    assert item["file_path"].startswith("assets/images/")

    assert client.get(f"/api/v1/images/{image_id}").status_code == 200
    assert client.get(f"/api/v1/images/{image_id}/content").status_code == 200
    versions = client.get(f"/api/v1/images/{image_id}/versions").json()
    assert versions["image"]["kind"] == "upscaled"
    assert versions["parent"] is None
    assert versions["children"] == []
