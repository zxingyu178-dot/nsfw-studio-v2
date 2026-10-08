"""ImageService / Gallery API 测试（Phase 2C，规范 §四十一-§四十九）。"""
from __future__ import annotations

import json

import pytest

from app.core.errors import ValidationError
from app.services import image_service


def test_import_engine_output(session, settings, png_bytes):
    from app.storage.manager import StorageManager
    from app.services import job_service

    storage = StorageManager(settings)
    job, _ = job_service.create_job(session, source="web", snapshot={
        "prompt_mode": "structured", "structured_prompt": {"style": "x"},
        "width": 832, "height": 1216, "count": 1, "seed_mode": "random",
    })
    item = job_service.get_items(session, job.id)[0]
    item.seed = 424242
    stage_item = job.stages[0].stage_items[0]  # Phase 3 §十四：导入按 StageItem 判定 kind/parent
    session.commit()

    image = image_service.import_engine_output(
        session, storage, data=png_bytes, original_filename="out_00001_.png",
        job=job, item=item, seed=424242, source="comfyui",
        metadata={"workflow_hash": "abc123"},
    )
    assert image.id.startswith("img_")
    assert image.file_path.startswith("images/originals/")
    assert ":" not in image.file_path, "禁止绝对路径入库"
    assert (image.width, image.height) == (1, 1)
    assert image.review_status == "UNREVIEWED" and image.favorite is False
    assert image.job_id == job.id and image.seed == 424242
    assert json.loads(image.metadata_json)["workflow_hash"] == "abc123"
    assert storage.absolutize(image.file_path).is_file()

    # StageItem 关联（Worker 回调路径）
    ids = image_service.import_adapter_outputs(session, storage, job, stage_item, [])
    assert ids == []


def test_import_rejects_garbage(session, settings):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    with pytest.raises(ValidationError):
        image_service.import_engine_output(
            session, storage, data=b"garbage", original_filename="x.png", source="comfyui",
        )


def _make_job_item(session):
    from app.services import job_service

    job, _ = job_service.create_job(session, source="web", snapshot={
        "prompt_mode": "structured", "structured_prompt": {"style": "x"},
        "width": 832, "height": 1216, "count": 1, "seed_mode": "random",
    })
    item = job_service.get_items(session, job.id)[0]
    session.commit()
    return job, job.stages[0].stage_items[0]


def _dir_entries(path) -> list:
    return list(path.iterdir()) if path.exists() else []


def test_import_batch_atomic_valid_plus_corrupt(session, settings, png_bytes):
    """Phase 2.2 §1：合法 PNG + 损坏 PNG → 整批失败，images=0，无任何残留。"""
    from app.engine.base import EngineOutputFile
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    job, stage_item = _make_job_item(session)
    outputs = [
        EngineOutputFile(filename="good.png", data=png_bytes),
        EngineOutputFile(filename="bad.png", data=b"this is not an image"),
    ]
    with pytest.raises(ValidationError):
        image_service.import_adapter_outputs(session, storage, job, stage_item, outputs)

    assert image_service.list_images(session, job_id=job.id)[1] == 0, "整批失败不得留下半成功图片"
    assert _dir_entries(storage.resolve_under("images/originals")) == [], "originals 不得有残留"
    assert _dir_entries(storage.temp_dir) == [], "temp 不得有残留"


def test_import_batch_two_valid_outputs_succeed_together(session, settings, png_bytes):
    """Phase 2.2 §1：两个合法输出在同一批次同时成功。"""
    from app.engine.base import EngineOutputFile
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    job, stage_item = _make_job_item(session)
    outputs = [
        EngineOutputFile(filename="a.png", data=png_bytes),
        EngineOutputFile(filename="b.png", data=png_bytes),
    ]
    image_ids = image_service.import_adapter_outputs(session, storage, job, stage_item, outputs)

    assert len(image_ids) == 2 and len(set(image_ids)) == 2
    images, total = image_service.list_images(session, job_id=job.id)
    assert total == 2
    for image in images:
        assert storage.absolutize(image.file_path).is_file()


def test_import_batch_rolls_back_when_move_fails(session, settings, png_bytes, monkeypatch):
    """Phase 2.2 §1：移动到正式目录阶段失败 → 回滚 DB 并删除本批次已建的全部文件。"""
    from app.engine.base import EngineOutputFile
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    job, stage_item = _make_job_item(session)
    original_move = storage.atomic_move_into
    calls = {"count": 0}

    def failing_move(temp_path, final_dir, name):
        calls["count"] += 1
        if calls["count"] == 2:  # 第一张已移动成功，第二张失败
            raise OSError("模拟磁盘错误")
        return original_move(temp_path, final_dir, name)

    monkeypatch.setattr(storage, "atomic_move_into", failing_move)
    outputs = [
        EngineOutputFile(filename="a.png", data=png_bytes),
        EngineOutputFile(filename="b.png", data=png_bytes),
    ]
    with pytest.raises(OSError):
        image_service.import_adapter_outputs(session, storage, job, stage_item, outputs)

    assert image_service.list_images(session, job_id=job.id)[1] == 0
    assert _dir_entries(storage.resolve_under("images/originals")) == [], \
        "第一张已移动成功的正式文件也必须随整批回滚删除"
    assert _dir_entries(storage.temp_dir) == []


def test_review_and_favorite(session, settings, png_bytes):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = image_service.import_engine_output(
        session, storage, data=png_bytes, original_filename="a.png", source="comfyui"
    )
    kept = image_service.set_review(session, image.id, "KEPT")
    assert kept.review_status == "KEPT"
    with pytest.raises(ValidationError):
        image_service.set_review(session, image.id, "MAYBE")
    fav = image_service.set_favorite(session, image.id, True)
    assert fav.favorite is True


def test_list_filters_and_job_summary(session, settings, png_bytes):
    from app.storage.manager import StorageManager
    from app.services import job_service

    storage = StorageManager(settings)
    job, _ = job_service.create_job(session, source="web", snapshot={
        "prompt_mode": "full", "full_prompt": "x", "count": 3, "seed_mode": "random",
    })
    for _ in range(3):
        image = image_service.import_engine_output(
            session, storage, data=png_bytes, original_filename="a.png",
            job=job, seed=1, source="comfyui",
        )
    image_service.set_review(session, image.id, "KEPT")

    items, total = image_service.list_images(session, job_id=job.id)
    assert total == 3
    _, total = image_service.list_images(session, job_id=job.id, review_status="KEPT")
    assert total == 1
    summary = image_service.job_gallery_summary(session, job.id)
    assert summary == {
        "job_id": job.id, "total": 3, "unreviewed": 2, "kept": 1, "rejected": 0, "favorites": 0,
    }


def test_image_api_flow(client, png_bytes):
    """Gallery API：content / review / favorite / workbench（§四十四、§四十七）。"""
    # 经完整栈：先造一个 job（comfyui 默认引擎在测试中不提交真实任务，直接用 API 查询空图库）
    listed = client.get("/api/v1/images")
    assert listed.status_code == 200
    assert listed.json()["total"] == 0

    # 直接经服务导入（含 job 关联）再走 API
    with client.app.state.session_factory() as session:
        from app.storage.manager import StorageManager
        from app.services import job_service

        storage = StorageManager(client.app.state.settings)
        job, _ = job_service.create_job(session, source="web", snapshot={
            "prompt_mode": "structured", "structured_prompt": {"style": "s"},
            "count": 1, "seed_mode": "random", "width": 512, "height": 512,
        })
        item = job_service.get_items(session, job.id)[0]
        item.seed = 777
        session.commit()
        image = image_service.import_engine_output(
            session, storage, data=png_bytes, original_filename="a.png",
            job=job, item=item, seed=777, source="comfyui",
        )
        image_id = image.id
        job_id = job.id

    content = client.get(f"/api/v1/images/{image_id}/content")
    assert content.status_code == 200
    assert content.headers["content-type"] == "image/png"

    reviewed = client.patch(f"/api/v1/images/{image_id}/review", json={"review_status": "KEPT"}).json()
    assert reviewed["review_status"] == "KEPT"
    fav = client.patch(f"/api/v1/images/{image_id}/favorite", json={"favorite": True}).json()
    assert fav["favorite"] is True

    # Image → Workbench：恢复 Job 当时快照 + 提供该图 Seed（规范 §四十七）
    wb = client.get(f"/api/v1/images/{image_id}/workbench").json()
    assert wb["image_id"] == image_id
    assert wb["seed"] == 777
    assert wb["snapshot"]["structured_prompt"]["style"] == "s"

    # 按 Job 统计（§四十九：未审核 / 保留 / 收藏 / 淘汰）
    summary = client.get(f"/api/v1/images/by-job/{job_id}/summary").json()
    assert summary["total"] == 1
    assert summary["kept"] == 1 and summary["favorites"] == 1
