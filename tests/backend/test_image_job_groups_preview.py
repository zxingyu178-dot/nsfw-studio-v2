"""Job 分组预览图：每组返回最新四张图片，且不改变分页语义。"""
from __future__ import annotations

from sqlalchemy import event

from app.core.ids import IMAGE, JOB, new_id
from app.models import Image, Job


def _make_completed_job(session, *, created_at: str, image_times: list[str]):
    job = Job(
        id=new_id(JOB),
        source="web",
        prompt_mode="full",
        workbench_snapshot_json="{}",
        generation_settings_json="{}",
        requested_count=len(image_times),
        status="COMPLETED",
        job_kind="generate",
        module_id="basic_generate",
        created_at=created_at,
    )
    session.add(job)
    session.flush()

    image_ids = []
    for created_index, image_created_at in enumerate(image_times):
        image_id = new_id(IMAGE)
        session.add(
            Image(
                id=image_id,
                job_id=job.id,
                file_path=f"images/originals/{image_id}/{created_index}.png",
                width=32,
                height=32,
                source="mock",
                created_at=image_created_at,
            )
        )
        image_ids.append(image_id)
    session.commit()
    return job, image_ids


def test_job_group_preview_returns_latest_four_in_descending_order(session):
    from app.services import image_service

    _job, image_ids = _make_completed_job(
        session,
        created_at="2026-10-20T01:00:00+00:00",
        image_times=[f"2026-10-20T01:00:0{i}+00:00" for i in range(6)],
    )

    statements: list[str] = []
    engine = session.get_bind()

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        groups, total = image_service.list_job_groups(session, page=1, page_size=20)
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert total == 1
    assert groups[0]["preview_image_ids"] == list(reversed(image_ids))[:4]
    assert len(statements) == 3  # 总数、当前页聚合、当前页全部 Job 的预览图各一次。
    preview_sql = " ".join(statements[-1].split())
    assert "WHERE images.job_id IN" in preview_sql
    assert "ORDER BY images.created_at DESC, images.id DESC" in preview_sql


def test_job_group_preview_does_not_mix_images_between_jobs(session):
    from app.services import image_service

    job_a, ids_a = _make_completed_job(
        session,
        created_at="2026-10-20T02:00:00+00:00",
        image_times=[f"2026-10-20T02:00:0{i}+00:00" for i in range(5)],
    )
    job_b, ids_b = _make_completed_job(
        session,
        created_at="2026-10-20T03:00:00+00:00",
        image_times=[f"2026-10-20T03:00:0{i}+00:00" for i in range(5)],
    )

    groups, total = image_service.list_job_groups(session, page=1, page_size=20)
    by_job_id = {group["job_id"]: group for group in groups}

    assert total == 2
    assert by_job_id[job_a.id]["preview_image_ids"] == list(reversed(ids_a))[:4]
    assert by_job_id[job_b.id]["preview_image_ids"] == list(reversed(ids_b))[:4]


def test_job_group_preview_keeps_api_pagination_and_total(client):
    image_ids_by_job: dict[str, list[str]] = {}
    with client.app.state.session_factory() as session:
        for index in range(3):
            job, image_ids = _make_completed_job(
                session,
                created_at=f"2026-10-20T0{index + 1}:00:00+00:00",
                image_times=[f"2026-10-20T0{index + 1}:00:00+00:00"],
            )
            image_ids_by_job[job.id] = image_ids

    response = client.get("/api/v1/images/job-groups", params={"page": 1, "page_size": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["has_next"] is True
    assert len(body["items"]) == 2
    for group in body["items"]:
        assert group["preview_image_ids"] == image_ids_by_job[group["job_id"]]
