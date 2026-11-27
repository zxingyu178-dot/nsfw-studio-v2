"""图库按底模筛选：列表 / 统计 / ID / 任务分组 / 下拉同源，__none__ 覆盖未记录与导入图。"""
from __future__ import annotations

import io
import json

from PIL import Image as PILImage

from app.models import Job


def _png(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (24, 24), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _job(session, job_id: str, model: str | None = None):
    config = {"model": model} if model is not None else {}
    job = Job(
        id=job_id, source="agent", status="COMPLETED", prompt_mode="full",
        positive_prompt_snapshot="probe", negative_prompt_snapshot="",
        generation_settings_json="{}", workbench_snapshot_json="{}",
        workflow_snapshot_json=json.dumps({
            "modules": [{"module_id": "anime_generate", "config": config}],
        }),
        requested_count=1, completed_count=1, module_id="anime_generate",
    )
    session.add(job)
    session.flush()
    return job


def test_gallery_model_filter_list_stats_ids_models_and_groups(client, session_factory, settings):
    from app.services import image_service
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    with session_factory() as session:
        job_a = _job(session, "job_model_a", " NoobAI-XL-v1.1.safetensors ")
        job_b = _job(session, "job_model_b", "miaomiaoHarem_v14.safetensors")
        job_none = _job(session, "job_model_none")
        images_a = [
            image_service.import_engine_output(
                session, storage, data=_png((10, 20, 30)), original_filename=f"a{i}.png",
                job=job_a, source="comfyui",
            )
            for i in range(2)
        ]
        image_b = image_service.import_engine_output(
            session, storage, data=_png((40, 50, 60)), original_filename="b.png",
            job=job_b, source="comfyui",
        )
        image_none = image_service.import_engine_output(
            session, storage, data=_png((70, 80, 90)), original_filename="none.png",
            job=job_none, source="comfyui",
        )
        imported = image_service.import_engine_output(
            session, storage, data=_png((100, 110, 120)), original_filename="import.png",
            source="import",
        )
        session.commit()
        ids_a = {image.id for image in images_a}
        ids_b = {image_b.id}
        ids_none = {image_none.id, imported.id}

    listed = client.get(
        "/api/v1/images", params={"model": "NoobAI-XL-v1.1.safetensors", "limit": 100},
    )
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()["items"]} == ids_a

    stats = client.get("/api/v1/images/stats", params={"model": "NoobAI-XL-v1.1.safetensors"})
    assert stats.status_code == 200 and stats.json()["total"] == 2

    ids = client.get("/api/v1/images/ids", params={"model": "miaomiaoHarem_v14.safetensors"})
    assert ids.status_code == 200
    assert set(ids.json()["ids"]) == ids_b and ids.json()["total"] == 1

    none_listed = client.get("/api/v1/images", params={"model": "__none__", "limit": 100})
    assert none_listed.status_code == 200
    assert {item["id"] for item in none_listed.json()["items"]} == ids_none

    models = client.get("/api/v1/images/models")
    assert models.status_code == 200
    items = {entry["model"]: entry["count"] for entry in models.json()["items"]}
    assert items == {
        "NoobAI-XL-v1.1.safetensors": 2,
        "miaomiaoHarem_v14.safetensors": 1,
    }

    groups = client.get(
        "/api/v1/images/job-groups",
        params={"model": "NoobAI-XL-v1.1.safetensors", "page_size": 20},
    )
    assert groups.status_code == 200
    body = groups.json()
    assert body["total"] == 1
    assert body["items"][0]["job_id"] == job_a.id
    assert body["items"][0]["model"] == "NoobAI-XL-v1.1.safetensors"
