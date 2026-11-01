"""图库「动漫」分类：Studio anime 产物 + V1 Anima 导入，列表与统计口径一致。"""
from __future__ import annotations

import io

from PIL import Image as PILImage

from app.models import Job


def _png(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (24, 24), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _job(session, job_id: str, module_id: str):
    job = Job(
        id=job_id, source="web", status="COMPLETED", prompt_mode="full",
        positive_prompt_snapshot="probe", negative_prompt_snapshot="",
        generation_settings_json="{}", workbench_snapshot_json="{}",
        requested_count=1, completed_count=1, module_id=module_id,
    )
    session.add(job)
    session.flush()
    return job


def test_gallery_anime_category_filters_module_and_import(
    client, session_factory, settings,
):
    from app.services import image_service
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    with session_factory() as session:
        anime_job = _job(session, "job_anime_cat", "anime_generate")
        basic_job = _job(session, "job_basic_cat", "basic_generate")
        anime = image_service.import_engine_output(
            session, storage, data=_png((10, 20, 30)), original_filename="anime.png",
            job=anime_job, source="comfyui",
        )
        basic = image_service.import_engine_output(
            session, storage, data=_png((40, 50, 60)), original_filename="basic.png",
            job=basic_job, source="comfyui",
        )
        imported_anima = image_service.import_engine_output(
            session, storage, data=_png((70, 80, 90)), original_filename="Anima_x.png",
            source="import",
            metadata={"v1_output": {"sources": [{"path": "D:/out/Anima_x.png"}]}},
        )
        imported_plain = image_service.import_engine_output(
            session, storage, data=_png((100, 110, 120)), original_filename="plain.png",
            source="import", metadata={"v1_output": {"sources": [{"path": "D:/out/plain.png"}]}},
        )
        session.commit()
        anime_id, basic_id = anime.id, basic.id
        anima_import_id, plain_import_id = imported_anima.id, imported_plain.id

    response = client.get("/api/v1/images", params={"category": "anime", "limit": 100})
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert ids == {anime_id, anima_import_id}
    assert basic_id not in ids and plain_import_id not in ids

    stats = client.get("/api/v1/images/stats", params={"category": "anime"})
    assert stats.status_code == 200
    assert stats.json()["total"] == 2

    imported = client.get("/api/v1/images", params={"category": "imported", "limit": 100})
    imported_ids = {item["id"] for item in imported.json()["items"]}
    assert imported_ids == {anima_import_id, plain_import_id}
