"""v0.13.2 事故修复测试：启动不自动重放陈旧 QUEUED/PAUSED，可显式清理。"""
from __future__ import annotations


def _make_job(session, status, job_id="j1"):
    from app.models.job import Job
    j = Job(id=job_id, source="web", status=status, prompt_mode="structured",
            workbench_snapshot_json="{}", generation_settings_json="{}",
            requested_count=1)
    session.add(j)
    session.commit()
    return j


def test_startup_flips_queued_and_paused_to_interrupted(session_factory):
    """遗留 QUEUED/RUNNING/PAUSED 启动时一律 INTERRUPTED（不自动重提引擎）。"""
    from app.services import job_service
    with session_factory() as session:
        _make_job(session, "QUEUED", "q1")
        _make_job(session, "RUNNING", "r1")
        _make_job(session, "PAUSED", "p1")
        _make_job(session, "COMPLETED", "c1")
        ids = job_service.mark_interrupted_at_startup(session)
    assert set(ids) == {"q1", "r1", "p1"}
    with session_factory() as session:
        from app.models.job import Job
        from sqlalchemy import select
        rows = {j.id: j.status for j in session.execute(select(Job)).scalars()}
        assert rows["q1"] == "INTERRUPTED"
        assert rows["r1"] == "INTERRUPTED"
        assert rows["p1"] == "INTERRUPTED"
        assert rows["c1"] == "COMPLETED"


def test_clear_stale_jobs_cancels_all_active(session_factory):
    """显式"清理陈旧任务"：所有非终态置 CANCELLED。"""
    from app.services import job_service
    with session_factory() as session:
        _make_job(session, "QUEUED", "q1")
        _make_job(session, "INTERRUPTED", "i1")
        _make_job(session, "COMPLETED", "c1")
        result = job_service.clear_stale_jobs(session)
    assert result["cancelled"] == 2
    with session_factory() as session:
        from app.models.job import Job
        from sqlalchemy import select
        rows = {j.id: j.status for j in session.execute(select(Job)).scalars()}
        assert rows["q1"] == "CANCELLED"
        assert rows["i1"] == "CANCELLED"
        assert rows["c1"] == "COMPLETED"


def test_clear_stale_endpoint(client, session_factory):
    """POST /api/v1/jobs/queue/clear-stale 路由可用（Desktop loopback）。"""
    from app.services import job_service
    with session_factory() as session:
        _make_job(session, "QUEUED", "q1")
    r = client.post("/api/v1/queue/clear-stale")
    assert r.status_code == 200
    assert r.json()["cancelled"] >= 1
