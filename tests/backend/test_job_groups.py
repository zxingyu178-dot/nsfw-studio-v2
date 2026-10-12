"""Phase 0.11.1 P1-2：Job 分组聚合（避免 N+1）测试。

- 多 Job 聚合各计数正确；
- 分页可访问早期 Job；
- 与单 Job summary 口径一致。
"""
from __future__ import annotations

import io

from PIL import Image as PILImage

from app.core.ids import JOB, new_id
from app.models import Job


def _png() -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (32, 32), (5, 5, 5)).save(buffer, format="PNG")
    return buffer.getvalue()


def _make_completed_job(session, storage, n_images: int):
    """直接构造 status=COMPLETED 的 Job（绕过 QueueWorker，避免被 worker 抢先处理）。"""
    from app.services import image_service

    job = Job(
        id=new_id(JOB),
        source="web",
        prompt_mode="full",
        workbench_snapshot_json="{}",
        generation_settings_json="{}",
        requested_count=n_images,
        status="COMPLETED",
        job_kind="generate",
        module_id="basic_generate",
    )
    session.add(job)
    session.commit()
    ids = []
    for _ in range(n_images):
        img = image_service.import_engine_output(
            session, storage, data=_png(), original_filename="a.png", job=job,
            seed=1, source="comfyui",
        )
        ids.append(img.id)
    return job, ids


def test_job_groups_aggregation_matches_single_summary(session, settings):
    from app.services import image_service
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    job_a, ids_a = _make_completed_job(session, storage, 3)
    job_b, ids_b = _make_completed_job(session, storage, 2)

    # A: 1 KEEP, 1 REJECT, 1 NEW; 收藏 1
    image_service.set_image_status(session, ids_a[0], "KEEP")
    image_service.set_image_status(session, ids_a[1], "REJECT")
    image_service.set_favorite(session, ids_a[0], True)
    # B: 全部 KEEP
    for iid in ids_b:
        image_service.set_image_status(session, iid, "KEEP")

    groups, total = image_service.list_job_groups(session, page=1, page_size=20)
    assert total == 2
    by_id = {g["job_id"]: g for g in groups}

    sa = image_service.job_gallery_summary(session, job_a.id)
    sb = image_service.job_gallery_summary(session, job_b.id)
    assert by_id[job_a.id]["total"] == sa["total"] == 3
    assert by_id[job_a.id]["unreviewed"] == sa["unreviewed"] == 1
    assert by_id[job_a.id]["kept"] == sa["kept"] == 1
    assert by_id[job_a.id]["rejected"] == sa["rejected"] == 1
    assert by_id[job_a.id]["favorites"] == sa["favorites"] == 1
    assert by_id[job_b.id]["total"] == sb["total"] == 2
    assert by_id[job_b.id]["kept"] == sb["kept"] == 2


def test_job_groups_paginates_to_early_jobs(client):
    from app.storage.manager import StorageManager

    storage = StorageManager(client.app.state.settings)
    job_ids = []
    with client.app.state.session_factory() as session:
        for _ in range(5):
            job, _ids = _make_completed_job(session, storage, 1)
            job_ids.append(job.id)

    # page_size=2 → 可翻到早期 Job（最早创建的在最后一页）
    seen = []
    page = 1
    while True:
        resp = client.get("/api/v1/images/job-groups", params={"page": page, "page_size": 2})
        assert resp.status_code == 200
        body = resp.json()
        seen.extend(g["job_id"] for g in body["items"])
        if not body["has_next"]:
            break
        page += 1
    assert len(seen) == 5
    assert set(seen) == set(job_ids)
    assert len(set(seen)) == 5

