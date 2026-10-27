"""一键恢复中断任务（POST /api/v1/jobs/resume-interrupted）。

覆盖：
- 纯排队（从未开始）任务：原地恢复 QUEUED，保留原 Job/Seed/提示词，排到队尾；
- 已部分完成：创建续跑子 Job，不修改父 Job；
- 重复调用幂等（不重复创建子 Job）；
- 无中断任务时返回空结构。
"""
from __future__ import annotations

import json

from app.models import Job, JobItem, JobStage, JobStageItem


def _make_unstarted_job(session) -> None:
    job = Job(
        id="job_queued_only", source="web", status="INTERRUPTED", prompt_mode="full",
        positive_prompt_snapshot="keep me prompt", workbench_snapshot_json='{"full_prompt":"keep me prompt"}',
        generation_settings_json="{}", requested_count=2, completed_count=0, queue_position=1,
    )
    session.add(job)
    session.add_all([
        JobItem(id="item_q0", job_id=job.id, item_index=0, status="INTERRUPTED", seed=42),
        JobItem(id="item_q1", job_id=job.id, item_index=1, status="INTERRUPTED", seed=43),
    ])
    stage = JobStage(
        id="stage_q0", job_id=job.id, stage_index=0, module_id="basic_generate",
        module_version="v1", provider="comfyui", status="INTERRUPTED", total_count=2,
    )
    session.add(stage)
    session.add_all([
        JobStageItem(id="si_q0", job_stage_id=stage.id, job_item_id="item_q0", item_index=0,
                     status="INTERRUPTED"),
        JobStageItem(id="si_q1", job_stage_id=stage.id, job_item_id="item_q1", item_index=1,
                     status="INTERRUPTED"),
    ])
    session.commit()


def test_requeue_unstarted_job_in_place(session_factory, settings):
    from app.services import job_service

    with session_factory() as session:
        _make_unstarted_job(session)
        result = job_service.resume_interrupted_jobs(session, settings)

    assert result["requeued"] == ["job_queued_only"]
    assert result["resumed"] == []
    assert result["remaining_images"] == 2

    with session_factory() as session:
        job = session.get(Job, "job_queued_only")
        assert job.status == "QUEUED"
        assert job.queue_position == 1
        assert job.error_type is None
        assert job.started_at is None
        items = {item.id: item for item in session.query(JobItem).all()}
        assert items["item_q0"].status == "QUEUED"
        assert items["item_q0"].seed == 42  # 原 Seed 不变
        assert items["item_q1"].seed == 43
        stage_items = {item.id: item for item in session.query(JobStageItem).all()}
        assert stage_items["si_q0"].status == "QUEUED"
        assert stage_items["si_q0"].engine_job_id is None

    # 再次调用：已不是 INTERRUPTED，不会重复恢复
    with session_factory() as session:
        again = job_service.resume_interrupted_jobs(session, settings)
    assert again["requeued_count"] == 0
    assert again["resumed_count"] == 0


def test_empty_when_no_interrupted_jobs(session_factory, settings):
    from app.services import job_service

    with session_factory() as session:
        result = job_service.resume_interrupted_jobs(session, settings)
    assert result == {
        "requeued": [], "resumed": [], "skipped": [], "errors": [],
        "requeued_count": 0, "resumed_count": 0, "remaining_images": 0,
    }


def _make_stale_workflow_job(session) -> None:
    """工作流改版前的旧 Job：快照里固化的是旧 workflow_hash / binding_hash。"""
    job = Job(
        id="job_stale_workflow", source="web", status="INTERRUPTED", prompt_mode="full",
        positive_prompt_snapshot="old workflow prompt",
        workbench_snapshot_json='{"full_prompt":"old workflow prompt"}',
        generation_settings_json="{}", requested_count=2, completed_count=0, queue_position=3,
        workflow_snapshot_json=json.dumps({"modules": [{
            "module_id": "basic_generate", "module_version": "v1", "provider": "comfyui",
            "binding_version": "v1", "workflow_hash": "oldhash", "binding_hash": "oldbind",
        }]}),
    )
    session.add(job)
    session.add_all([
        JobItem(id="item_s0", job_id=job.id, item_index=0, status="INTERRUPTED"),
        JobItem(id="item_s1", job_id=job.id, item_index=1, status="INTERRUPTED"),
    ])
    session.commit()


def test_stale_workflow_job_skipped_not_requeued(session_factory, settings, monkeypatch):
    """旧指纹任务：恢复时直接 skipped/WORKFLOW_CHANGED，不排队、不生成子 Job。"""
    from app.engine import factory
    from app.engine.base import EngineError
    from app.services import job_service

    def _raise_mismatch(_settings, _requested):
        raise EngineError("WORKFLOW_HASH_MISMATCH", "job=oldhash 磁盘=newhash")

    monkeypatch.setattr(factory, "resolve_workflow_modules", _raise_mismatch)

    with session_factory() as session:
        _make_stale_workflow_job(session)
        result = job_service.resume_interrupted_jobs(session, settings)

    assert result["requeued"] == []
    assert result["resumed"] == []
    assert result["skipped"] == [{
        "job_id": "job_stale_workflow", "reason": "WORKFLOW_CHANGED",
        "message": "WORKFLOW_HASH_MISMATCH: job=oldhash 磁盘=newhash",
    }]

    with session_factory() as session:
        # 原 Job 保持 INTERRUPTED，不被静默重排
        assert session.get(Job, "job_stale_workflow").status == "INTERRUPTED"


def test_partial_job_creates_child_and_is_idempotent(client, session_factory):
    client.post("/api/v1/queue/pause")
    try:
        response = client.post("/api/v1/jobs", json={
            "source": "web",
            "snapshot": {
                "prompt_mode": "full",
                "full_prompt": "partial resume prompt",
                "negative_prompt": "",
                "count": 2,
                "width": 768,
                "height": 1024,
                "seed_mode": "random",
                "workflow_modules": [{"module_id": "anime_generate"}],
                "input_images": [],
            },
        })
        assert response.status_code == 201, response.text
        parent_id = response.json()["id"]

        # 模拟启动恢复后的现场：父 Job 中断，第 0 张已完成，第 1 张未完成
        with session_factory() as session:
            job = session.get(Job, parent_id)
            job.status = "INTERRUPTED"
            job.completed_count = 1
            items = list(session.query(JobItem).filter(JobItem.job_id == parent_id).all())
            for index, item in enumerate(items):
                item.status = "COMPLETED" if index == 0 else "INTERRUPTED"
            session.commit()

        first = client.post("/api/v1/jobs/resume-interrupted")
        assert first.status_code == 200, first.text
        data = first.json()
        parent = next((entry for entry in data["resumed"] if entry["parent_job_id"] == parent_id), None)
        assert parent is not None
        assert data["resumed_count"] >= 1

        with session_factory() as session:
            child = session.get(Job, parent["child_job_id"])
            assert child is not None
            assert child.resume_of_job_id == parent_id
            assert child.requested_count == 1  # 只续剩余 1 张
            assert "partial resume prompt" in child.positive_prompt_snapshot
            assert session.get(Job, parent_id).status == "INTERRUPTED"

        second = client.post("/api/v1/jobs/resume-interrupted")
        assert second.status_code == 200
        second_data = second.json()
        assert not any(entry["parent_job_id"] == parent_id for entry in second_data["resumed"])
        assert any(entry["job_id"] == parent_id and entry["reason"] == "ALREADY_RESUMED"
                   for entry in second_data["skipped"])
    finally:
        client.post("/api/v1/queue/resume")
