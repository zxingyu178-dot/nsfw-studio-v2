"""Phase 5 测试：外部图片导入（hash 去重 / 部分失败）、输入图片冻结（Workbench → Recipe → Job）、
Face Asset 参考图、图片引用保护、Modules 能力声明（Gate B：零真实生图，全部离线 Mock）。
"""
from __future__ import annotations

import dataclasses
import json
import time

import pytest
from sqlalchemy import select, text

from app.core.config import Settings, WorkflowConfig
from app.core.errors import ValidationError
from app.database import init_database, make_engine
from app.main import create_app
from app.models import AssetReferenceImage, Image, Job, JobStageItem, RecipeVersion
from app.services import image_reference_service, image_service, job_service
from app.storage.manager import StorageManager


# ===== 工具 =====

def webp_bytes(width: int = 64, height: int = 32) -> bytes:
    """最小合法 VP8L WebP（14-bit 宽高），用于验证 WEBP 导入与尺寸解析。"""
    bits = (width - 1) | ((height - 1) << 14)
    payload = b"\x2f" + bits.to_bytes(4, "little")
    chunk = b"VP8L" + len(payload).to_bytes(4, "little") + payload
    body = b"WEBP" + chunk + b"\x00" * 6  # 补齐到解析所需最小长度
    return b"RIFF" + len(body).to_bytes(4, "little") + body


def import_files(client, files: list[tuple[str, bytes, str]]):
    return client.post(
        "/api/v1/images/import",
        files=[("files", (name, data, content_type)) for name, data, content_type in files],
    )


def import_one(client, name: str, data: bytes, content_type: str = "image/png") -> dict:
    response = import_files(client, [(name, data, content_type)])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["imported_count"] == 1, body
    return body["imported"][0]["image"]


def make_snapshot(count: int = 1, **overrides) -> dict:
    snapshot = {
        "prompt_mode": "structured",
        "structured_prompt": {"style": "anime", "scene": "cafe"},
        "full_prompt": "",
        "negative_prompt": "blurry",
        "selected_assets": {},
        "width": 512,
        "height": 768,
        "count": count,
        "seed_mode": "random",
        "workflow_modules": [],
    }
    snapshot.update(overrides)
    return snapshot


def mock_settings(settings: Settings, **options) -> Settings:
    merged = {"worker_poll_interval_ms": 20, "engine_poll_ms": 20}
    merged.update(options)
    return dataclasses.replace(
        settings,
        workflow=WorkflowConfig(raw={"engine": {"provider": "mock", "options": merged}}),
    )


def wait_for(client, job_id: str, predicate, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/api/v1/jobs/{job_id}").json()
        if predicate(last):
            return last
        time.sleep(0.05)
    raise AssertionError(f"等待任务状态超时: {json.dumps(last, ensure_ascii=False)[:500]}")


@pytest.fixture()
def mock_client(settings):
    from fastapi.testclient import TestClient

    app = create_app(mock_settings(settings))
    with TestClient(app) as test_client:
        yield test_client


# ===== §三/§四/§五/§六：外部导入 =====

def test_import_single_png_into_gallery(client, settings, session, png_bytes):
    """导入 → 校验 → 复制进 DataRoot/images/originals/ → Image 数据库 → Gallery。"""
    image = import_one(client, "桌面图片.png", png_bytes)
    assert image["source"] == "import" and image["kind"] == "original"
    assert image["job_id"] is None and image["job_item_id"] is None
    assert image["file_path"].startswith("images/originals/") and ":" not in image["file_path"]
    assert (image["width"], image["height"]) == (1, 1)

    stored = session.get(Image, image["id"])
    assert stored is not None and stored.imported_filename == "桌面图片.png"
    assert stored.sha256 and len(stored.sha256) == 64
    assert StorageManager(settings).absolutize(stored.file_path).is_file()

    # 图库可见（source=import 过滤）
    listing = client.get("/api/v1/images", params={"source": "import"}).json()
    assert any(item["id"] == image["id"] for item in listing["items"])

    # §四：外部导入没有生成上下文（Provenance 如实标记，不伪造生成历史）
    provenance = client.get(f"/api/v1/images/{image['id']}/provenance").json()
    assert provenance["job_id"] is None and provenance["root_image_id"] == image["id"]
    workbench = client.get(f"/api/v1/images/{image['id']}/workbench")
    assert workbench.status_code == 404
    assert workbench.json()["error"]["code"] == "IMAGE_NO_GENERATION_CONTEXT"


def test_import_webp_with_dimensions(client, png_bytes):
    """WEBP 是合同要求支持的格式；导入时宽高必须解析成功（不是 0x0）。"""
    image = import_one(client, "sample.webp", webp_bytes(200, 100), "image/webp")
    assert (image["width"], image["height"]) == (200, 100)


def test_import_sha256_dedup(client, png_bytes):
    """§六：同一文件重复导入 → 提示已存在，默认不创建第二份。"""
    first = import_one(client, "a.png", png_bytes)
    response = import_files(client, [("copy_of_a.png", png_bytes, "image/png")])
    body = response.json()
    assert body["imported_count"] == 0 and body["duplicate_count"] == 1
    assert body["duplicates"][0]["image_id"] == first["id"]

    total = client.get("/api/v1/images", params={"source": "import"}).json()["total"]
    assert total == 1, "重复导入不得创建第二份图片"


def test_import_partial_failure_not_all_or_nothing(client, png_bytes):
    """§二十三：单张失败不影响整批（与生成输出整批事务语义不同，这是文件管理操作）。"""
    altered = png_bytes + b"\x01"  # 与 png_bytes 内容不同 → 不是重复
    response = import_files(client, [
        ("ok.png", altered, "image/png"),
        ("not_image.png", b"this is not an image", "image/png"),
        ("wrong_ext.gif", png_bytes, "image/gif"),
    ])
    body = response.json()
    assert body["imported_count"] == 1
    assert body["failed_count"] == 2
    assert {item["filename"] for item in body["failed"]} == {"not_image.png", "wrong_ext.gif"}
    assert all(item["error_code"] for item in body["failed"])


def test_import_rejects_oversize(client, settings):
    from app.core.filetypes import MAX_UPLOAD_BYTES

    oversized = b"\x89PNG\r\n\x1a\n" + b"\x00" * (MAX_UPLOAD_BYTES + 10)
    response = import_files(client, [("big.png", oversized, "image/png")])
    body = response.json()
    assert body["imported_count"] == 0 and body["failed_count"] == 1
    assert body["failed"][0]["error_code"] == "FILE_TOO_LARGE"


# ===== §八/§十：Workbench 输入图片 → Job 冻结 =====

def test_job_rejects_input_image_ignored_by_module(mock_client, png_bytes):
    """Phase 5.1 Task4（P0）：输入图片不能被静默忽略。

    Workbench 提供 input_image 但 Pipeline 首个模块 basic_generate 不消费输入图
    → Job 创建必须被拒绝（UNUSED_INPUT_IMAGE），不允许"看似用了图，实际跑成文生图"。
    """
    image = import_one(mock_client, "source.png", png_bytes)
    snapshot = make_snapshot(count=2, input_images=[{"role": "source", "image_id": image["id"]}])
    response = mock_client.post("/api/v1/jobs", json={"snapshot": snapshot})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "UNUSED_INPUT_IMAGE"


def test_job_creation_validates_input_image_exists(client):
    response = client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(input_images=[{"role": "source", "image_id": "img_missing"}]),
    })
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "IMAGE_NOT_FOUND"


def test_job_rejects_multiple_input_images(client, png_bytes):
    """§八：第一版 max=1（schema 直接拒绝，不进入业务层）。"""
    image = import_one(client, "one.png", png_bytes)
    response = client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(input_images=[
            {"role": "source", "image_id": image["id"]},
            {"role": "source", "image_id": image["id"]},
        ]),
    })
    assert response.status_code == 422


def test_process_job_snapshot_input_mismatch_rejected(session, settings, png_bytes):
    """处理型 Job：快照输入图（若携带）必须与 input_image_ids 一致，禁止两个事实源打架。"""
    storage = StorageManager(settings)
    images = image_service.import_images_batch(session, storage, [
        ("a.png", "image/png", png_bytes),
        ("b.png", "image/png", png_bytes + b"\x02"),
    ]).imported
    with pytest.raises(ValidationError) as error:
        job_service.create_job(
            session, source="web",
            snapshot={**make_snapshot(), "input_images": [{"role": "source", "image_id": images[0].id}]},
            workflow_modules=[{"module_id": "upscale", "module_version": "v1"}],
            job_kind="process", input_image_ids=[images[1].id],
        )
    assert error.value.code == "PIPELINE_INVALID"


# ===== §九：Recipe 输入图快照 =====

def test_recipe_snapshots_input_images_with_hash(client, png_bytes):
    image = import_one(client, "recipe_src.png", png_bytes)
    snapshot = make_snapshot(input_images=[{"role": "source", "image_id": image["id"]}])
    response = client.post("/api/v1/recipes", json={"name": "图生图配方", "snapshot": snapshot})
    assert response.status_code == 201, response.text
    recipe = response.json()
    version = recipe["current_version"]
    assert len(version["input_images"]) == 1
    ref = version["input_images"][0]
    assert ref["role"] == "source" and ref["image_id"] == image["id"]
    assert ref["sha256"] and len(ref["sha256"]) == 64
    assert ref["missing"] is False

    # 内容完全一致 → 不产生新版本（input_images 参与 signature 比较）
    again = client.post(f"/api/v1/recipes/{recipe['id']}/versions", json={"name": "图生图配方", "snapshot": snapshot})
    assert again.status_code == 201
    assert again.json()["version_no"] == version["version_no"]

    # §九：恢复旧版本必须复制输入图关系
    restored = client.post(
        f"/api/v1/recipes/{recipe['id']}/versions/{version['id']}/restore", json={}
    ).json()
    assert restored["version_no"] == version["version_no"] + 1
    assert restored["input_images"][0]["image_id"] == image["id"]


def test_recipe_input_image_missing_is_marked_not_cleared(client, session, png_bytes):
    """§九：图片不存在 → 明确显示"输入图片已丢失"，绝不静默清空。"""
    image = import_one(client, "will_vanish.png", png_bytes)
    recipe = client.post("/api/v1/recipes", json={
        "name": "会丢图的配方",
        "snapshot": make_snapshot(input_images=[{"role": "source", "image_id": image["id"]}]),
    }).json()

    stored = session.get(Image, image["id"])
    session.delete(stored)
    session.commit()

    detail = client.get(f"/api/v1/recipes/{recipe['id']}").json()
    ref = detail["current_version"]["input_images"][0]
    assert ref["image_id"] == image["id"], "引用必须保留（不得静默清空）"
    assert ref["missing"] is True


def test_recipe_rejects_unknown_input_image(client):
    response = client.post("/api/v1/recipes", json={
        "name": "未知输入图",
        "snapshot": make_snapshot(input_images=[{"role": "source", "image_id": "img_nope"}]),
    })
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "IMAGE_NOT_FOUND"


# ===== §十二/§十三：Face Asset Reference Image =====

def test_face_asset_binds_gallery_reference_image(client, png_bytes):
    image = import_one(client, "face_ref.png", png_bytes)
    response = client.post("/api/v1/assets", data={
        "name": "测试人脸", "type": "face", "reference_image_id": image["id"],
    })
    assert response.status_code == 201, response.text
    asset = response.json()
    assert asset["current_version"]["reference_images"] == [image["id"]]

    # 新增版本换参考图（内容变化 → 新版本；旧版本保留）
    image2 = import_one(client, "face_ref2.png", png_bytes + b"\x03")
    version2 = client.post(f"/api/v1/assets/{asset['id']}/versions", data={
        "reference_image_id": image2["id"],
    }).json()
    assert version2["version_no"] == 2
    assert version2["reference_images"] == [image2["id"]]

    # 不传参考图 → 沿用当前版本参考图；无其他变化 → 不创建新版本
    version3 = client.post(f"/api/v1/assets/{asset['id']}/versions", data={}).json()
    assert version3["version_no"] == 2
    assert version3["reference_images"] == [image2["id"]]

    # 版本历史中旧版本各自保留自己的参考图
    versions = client.get(f"/api/v1/assets/{asset['id']}/versions").json()
    by_no = {item["version_no"]: item for item in versions}
    assert by_no[1]["reference_images"] == [image["id"]]
    assert by_no[2]["reference_images"] == [image2["id"]]


def test_asset_reference_requires_face_type_and_existing_image(client, png_bytes):
    image = import_one(client, "ref_check.png", png_bytes)
    response = client.post("/api/v1/assets", data={
        "name": "场景素材", "type": "scene", "reference_image_id": image["id"],
    })
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ASSET_REFERENCE_TYPE_INVALID"

    response = client.post("/api/v1/assets", data={
        "name": "人脸素材", "type": "face", "reference_image_id": "img_missing",
    })
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "IMAGE_NOT_FOUND"


# ===== §十一：图片引用保护 =====

def test_image_reference_counts_across_all_sources(mock_client, session, png_bytes):
    """图片被 Recipe / StageItem / Asset Reference / 派生图 / Asset 溯源引用时全部可识别。"""
    image = import_one(mock_client, "shared.png", png_bytes)

    # 1) Recipe 引用
    mock_client.post("/api/v1/recipes", json={
        "name": "引用配方",
        "snapshot": make_snapshot(input_images=[{"role": "source", "image_id": image["id"]}]),
    })
    # 2) Face Asset 参考图 + 3) Asset 溯源
    mock_client.post("/api/v1/assets", data={
        "name": "引用人脸", "type": "face", "reference_image_id": image["id"],
    })
    mock_client.post("/api/v1/assets", data={
        "name": "溯源素材", "type": "scene", "source_image_id": image["id"],
    })
    # 4) 处理型 Job（StageItem 输入）→ 产出派生图（parent_image_id）
    job = mock_client.post("/api/v1/images/upscale", json={"image_ids": [image["id"]]}).json()
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")
    child_id = final["stages"][0]["items"][0]["output_image_id"]
    assert child_id

    response = mock_client.get(f"/api/v1/images/{image['id']}/references")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    refs = body["references"]
    assert len(refs["recipe_ids"]) == 1
    assert len(refs["stage_item_ids"]) == 1
    assert len(refs["reference_asset_ids"]) == 1
    assert len(refs["source_asset_ids"]) == 1
    assert refs["derived_image_ids"] == [child_id]
    assert body["active_job_ids"] == []  # 任务已完成

    # 未被引用的图片：total=0
    lone = import_one(mock_client, "lone.png", png_bytes + b"\x04")
    assert mock_client.get(f"/api/v1/images/{lone['id']}/references").json()["total"] == 0


# ===== §十四：ModuleCapabilities 输入声明（Gate B 判定依据） =====

def test_modules_api_declares_input_capabilities(client):
    modules = {item["module_id"]: item for item in client.get("/api/v1/modules").json()}
    assert modules["basic_generate"]["input_required"] is False
    assert modules["upscale"]["input_required"] is True
    assert modules["upscale"]["input_role"] == "source"
    assert modules["upscale"]["output_kind"] == "upscaled"

    # Phase 5.1（Gate C）：img2img 已注册并可用，成为图片生成模式 Primary Module
    # （Phase 5 时的"无可用图片条件模块"Gate B 已解除；Gate 判定依据 available=true）
    img2img = modules["img2img"]
    assert img2img["registered"] is True
    assert img2img["available"] is True
    assert img2img["input_required"] is True
    assert img2img["output_kind"] == "processed"


# ===== 迁移 0010 =====

def test_migration_0010_schema_and_idempotency(settings, session):
    columns = {row[1] for row in session.execute(text("PRAGMA table_info(images)"))}
    assert {"sha256", "imported_filename"} <= columns
    recipe_columns = {row[1] for row in session.execute(text("PRAGMA table_info(recipe_versions)"))}
    assert "input_images_json" in recipe_columns
    tables = {row[0] for row in session.execute(
        text("SELECT name FROM sqlite_master WHERE type = 'table'")
    )}
    assert "asset_reference_images" in tables
    assert "idx_images_sha256" in {
        row[0] for row in session.execute(text("SELECT name FROM sqlite_master WHERE type = 'index'"))
    }

    engine = make_engine(settings.storage.database_path)
    try:
        assert init_database(engine) == [], "重复启动不得重复应用迁移"
    finally:
        engine.dispose()


# ===== 服务层直测：去重按内容（不是文件名）、引用行落库 =====

def test_import_service_dedup_by_content_not_filename(session, settings, png_bytes):
    storage = StorageManager(settings)
    first = image_service.import_images_batch(session, storage, [("one.png", "image/png", png_bytes)])
    second = image_service.import_images_batch(session, storage, [("totally_different_name.png", "image/png", png_bytes)])
    assert len(first.imported) == 1 and not first.duplicates
    assert not second.imported and second.duplicates[0]["image_id"] == first.imported[0].id

    # 引用行确实写入 asset_reference_images（role=face_reference）
    from app.services import asset_service

    image = first.imported[0]
    asset = asset_service.create_asset(
        session, storage, asset_type="face", name="引用行检查", reference_image_id=image.id,
    )
    current = asset_service.get_current_version(session, asset)
    assert asset_service.get_reference_image_ids(session, current.id) == [image.id]
    rows = session.execute(select(AssetReferenceImage).where(AssetReferenceImage.image_id == image.id)).scalars().all()
    assert len(rows) == 1 and rows[0].role == "face_reference" and rows[0].sort_order == 0