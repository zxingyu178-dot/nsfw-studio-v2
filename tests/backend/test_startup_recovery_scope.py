"""启动恢复的引擎核对范围：只核对"确实动过"的槽位，避免拖动启动超时。

场景：进程被强杀后重启，大量从未开始的排队槽位也处于 INTERRUPTED。
这些槽位不可能产生输出，逐个扫描引擎/文件只会拖慢启动（曾撞上载体 88 秒就绪超时）。
"""
from __future__ import annotations

import asyncio

import pytest

from app.engine.base import EngineAdapter
from app.workers.queue_worker import SingleQueueWorker


class _CountingAdapter(EngineAdapter):
    """记录扫描调用次数的假引擎：不连网、不产图。"""

    name = "counting"

    def __init__(self) -> None:
        self.scans = 0

    async def health(self):
        from app.engine.base import EngineHealth

        return EngineHealth(ok=True)

    async def submit_job(self, request):
        raise NotImplementedError

    async def get_job_status(self, engine_job_id: str):
        return None

    async def get_job_outputs(self, engine_job_id: str):
        return []

    async def cancel_job(self, engine_job_id: str) -> None:
        return None

    def scan_stage_outputs(self, ref, *, job_id: str, stage_index: int, stage_item_id: str):
        self.scans += 1
        return []


def _stage_item_of(session_factory, job_id: str):
    from app.models import JobStage, JobStageItem
    from app.services import job_service

    with session_factory() as session:
        job = job_service.get_job(session, job_id)
        stage = session.query(JobStage).filter_by(job_id=job.id).first()
        return session.query(JobStageItem).filter_by(job_stage_id=stage.id).first()


def _make_job(session_factory) -> str:
    from app.services import job_service

    with session_factory() as session:
        job, _ = job_service.create_job(
            session, source="web", snapshot=_snapshot()
        )
        return job.id


def _snapshot() -> dict:
    return {
        "prompt_mode": "full",
        "structured_prompt": {},
        "full_prompt": "1girl",
        "negative_prompt": "",
        "generation_mode": "text",
        "width": 1024,
        "height": 1024,
        "count": 1,
        "seed_mode": "random",
        "workflow_modules": [{"module_id": "basic_generate", "config": {}}],
        "input_images": [],
    }


def test_never_started_items_are_not_scanned(session_factory):
    job_id = _make_job(session_factory)
    adapter = _CountingAdapter()
    worker = SingleQueueWorker(session_factory, adapter)
    asyncio.run(worker.recover_interrupted())
    assert adapter.scans == 0


def test_started_items_are_still_reconciled(session_factory):
    job_id = _make_job(session_factory)
    from app.models import JobStageItem

    with session_factory() as session:
        item = session.query(JobStageItem).first()
        item.started_at = "2026-01-01T00:00:00Z"
        item.status = "RUNNING"
        session.commit()

    adapter = _CountingAdapter()
    worker = SingleQueueWorker(session_factory, adapter)
    asyncio.run(worker.recover_interrupted())
    assert adapter.scans == 1, "动过的槽位必须核对（引擎 history 或文件兜底）"
