"""v0.15 Task 6/7 真实 Step 进度合同 + 进度事件分流测试（hermetic）。

覆盖：
- EngineJobStatus 携带 step/max_step 字段，默认 None；
- ComfyUI progress WebSocket 事件的 value/max 保真为 step/max_step；
- 成功/失败终态清空 step（不允许 UI 停在 25/25）；
- ITEM_PROGRESS 是临时事件（只广播 SSE，不写 job_events）；
- 相同进度签名不重复落库，进度列按节流写入。
"""
from __future__ import annotations

import dataclasses
import time

import pytest

from app.core.config import Settings, WorkflowConfig


def make_snapshot(count: int = 1) -> dict:
    return {
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


# ===== EngineJobStatus 字段合同 =====

def test_engine_status_step_fields():
    """EngineJobStatus 新增 step/max_step：默认 None，可显式携带真实采样步数。"""
    from app.engine.base import EngineJobStatus

    idle = EngineJobStatus(state="running")
    assert idle.step is None and idle.max_step is None

    sampling = EngineJobStatus(state="running", progress=17 / 30, stage="sampling",
                               step=17, max_step=30)
    assert sampling.step == 17 and sampling.max_step == 30
    # 非采样阶段（如 upscale / save_image）必须显式为 None
    saving = EngineJobStatus(state="running", progress=1.0, stage="save_image")
    assert saving.step is None and saving.max_step is None


# ===== ComfyUI WebSocket 进度保真 =====

def _make_adapter_with_live_prompt():
    """构造 ComfyUIAdapter 并注入一个已 submit 的 live prompt（白盒，不发起任何 HTTP）。"""
    from app.engine.comfyui import ComfyUIAdapter

    adapter = ComfyUIAdapter(
        options={"websocket_progress": True},
        comfyui_config={"url": "http://127.0.0.1:8188"},
    )
    # 与 submit_job 成功后写入的 live 结构保持一致
    adapter._live["pid"] = {
        "stage": "queued", "progress": 0.0, "state": "queued",
        "step": None, "max_step": None,
        "error_type": "", "error_message": "", "updated": time.monotonic(),
    }
    return adapter


def test_comfy_progress_preserves_step():
    """ComfyUI progress 事件 value/max 必须映射为 step/max_step，且保留归一化 progress。"""
    adapter = _make_adapter_with_live_prompt()

    adapter._handle_ws_message(
        '{"type": "progress", "data": {"prompt_id": "pid", "value": 17, "max": 30}}'
    )
    live = adapter._live["pid"]
    assert live["step"] == 17 and live["max_step"] == 30
    assert live["progress"] == pytest.approx(17 / 30, abs=0.01)

    status = adapter._running_status(live)
    assert status.step == 17 and status.max_step == 30
    assert status.progress == pytest.approx(17 / 30, abs=0.01)

    # 公共查询路径（在引擎队列中，history 尚未出现）也必须携带 step
    async def no_history(engine_job_id):
        return None

    async def in_queue(engine_job_id):
        return True

    # 实例属性不会绑定 self，故 fake 只接收单参数
    adapter._history_state = no_history  # type: ignore[assignment]
    adapter._in_engine_queue = in_queue  # type: ignore[assignment]

    import asyncio
    public = asyncio.run(adapter.get_job_status("pid"))
    assert public.state == "running"
    assert public.step == 17 and public.max_step == 30


def test_progress_success_clears_step():
    """execution_success / execution_error 必须清空 step/max_step。"""
    adapter = _make_adapter_with_live_prompt()

    # 先采样到 17/30
    adapter._handle_ws_message(
        '{"type": "progress", "data": {"prompt_id": "pid", "value": 17, "max": 30}}'
    )
    assert adapter._live["pid"]["step"] == 17

    # 成功 → 进入保存图片阶段，step 清空
    adapter._handle_ws_message(
        '{"type": "execution_success", "data": {"prompt_id": "pid"}}'
    )
    live = adapter._live["pid"]
    assert live["step"] is None and live["max_step"] is None
    assert live["stage"] == "save_image" and live["progress"] == 1.0

    # 失败路径同样清空
    adapter2 = _make_adapter_with_live_prompt()
    adapter2._handle_ws_message(
        '{"type": "progress", "data": {"prompt_id": "pid", "value": 5, "max": 30}}'
    )
    adapter2._handle_ws_message(
        '{"type": "execution_error", "data": {"prompt_id": "pid", '
        '"node_type": "KSampler", "exception_message": "oom"}}'
    )
    assert adapter2._live["pid"]["step"] is None and adapter2._live["pid"]["max_step"] is None


# ===== Worker 临时事件 / 节流持久化 =====

class _CaptureBroker:
    """记录全部已发布事件的内存 broker（不做 SSE，避免跨事件循环队列）。"""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def attach_loop(self, loop) -> None:  # noqa: ANN001
        pass

    def subscribe(self):
        raise NotImplementedError

    def unsubscribe(self, queue) -> None:  # noqa: ANN001
        pass

    def publish(self, event: dict) -> None:
        self.events.append(event)

    def subscriber_count(self) -> int:
        return 0


def _make_job(session_factory):
    """直接经 JobService 创建一个单 StageItem 的 Job，返回 (job_id, stage_item_id, job_item_id)。"""
    from app.models import JobStage, JobStageItem
    from app.services import job_service

    with session_factory() as session:
        job, _ = job_service.create_job(session, source="web", snapshot=make_snapshot(1))
        stage = session.query(JobStage).filter_by(job_id=job.id).first()
        stage_item = session.query(JobStageItem).filter_by(job_stage_id=stage.id).first()
        return job.id, stage_item.id, stage_item.job_item_id


def test_progress_unchanged_does_not_write_event(session_factory):
    """相同进度签名只广播 SSE、不重复落库；进度列按节流写入；job_events 无 ITEM_PROGRESS。"""
    from app.engine.base import EngineJobStatus
    from app.engine.mock import MockEngineAdapter
    from app.models import JobEvent, JobStageItem
    from app.services import job_service
    from app.workers.queue_worker import SingleQueueWorker

    job_id, stage_item_id, job_item_id = _make_job(session_factory)
    broker = _CaptureBroker()
    original_broker = job_service._EVENT_BROKER
    job_service.set_event_broker(broker)
    try:
        worker = SingleQueueWorker(
            session_factory, MockEngineAdapter(),
            progress_persist_interval_ms=10_000,  # 测试中故意放大节流窗口
        )
        status = EngineJobStatus(state="running", progress=0.1, stage="sampling",
                                 step=1, max_step=10)
        # 同一签名连续 3 次：每次都广播 SSE，但只允许落库一次
        for _ in range(3):
            worker._update_stage_item_progress(
                job_id, stage_item_id, status,
                stage_index=0, job_item_id=job_item_id,
            )
        progress_events = [e for e in broker.events if e["type"] == "ITEM_PROGRESS"]
        assert len(progress_events) == 3, "每次轮询都应广播临时 SSE"

        with session_factory() as session:
            assert session.query(JobEvent).filter_by(event_type="ITEM_PROGRESS").count() == 0
            assert session.get(JobStageItem, stage_item_id).progress == pytest.approx(0.1)

        # 签名变化但处于节流窗口内 → 不落库（实时层已广播，最后进度由后续轮询补）
        worker._update_stage_item_progress(
            job_id, stage_item_id,
            EngineJobStatus(state="running", progress=0.2, stage="sampling", step=2, max_step=10),
            stage_index=0, job_item_id=job_item_id,
        )
        with session_factory() as session:
            assert session.get(JobStageItem, stage_item_id).progress == pytest.approx(0.1)

        # stage 切换立即落库（即使处于节流窗口），且 step 不入库
        worker._update_stage_item_progress(
            job_id, stage_item_id,
            EngineJobStatus(state="running", progress=0.95, stage="save_image",
                            step=None, max_step=None),
            stage_index=0, job_item_id=job_item_id,
        )
        with session_factory() as session:
            assert session.get(JobStageItem, stage_item_id).progress == pytest.approx(0.95)
            # 始终不允许出现 ITEM_PROGRESS 持久事件
            assert session.query(JobEvent).filter_by(event_type="ITEM_PROGRESS").count() == 0

        # 临时 SSE 必须携带真实 step
        stepped = [e for e in progress_events if e["payload"].get("step") == 1]
        assert stepped and stepped[0]["payload"]["max_step"] == 10
    finally:
        job_service.set_event_broker(original_broker)


def test_progress_event_is_transient(settings, monkeypatch):
    """端到端：采样过程中 SSE 广播 ITEM_PROGRESS（含 step），但 job_events 零持久化。"""
    from fastapi.testclient import TestClient

    from app.database.base import make_engine
    from app.engine.base import EngineJobStatus, EngineOutputFile
    from app.engine.mock import PNG_FIXTURE, MockEngineAdapter
    from app.main import create_app
    from app.models import JobEvent
    from app.services import job_service

    calls = {"n": 0}

    async def fake_status(self, engine_job_id):
        calls["n"] += 1
        if calls["n"] < 6:
            return EngineJobStatus(state="running", progress=0.5, stage="sampling",
                                   step=calls["n"], max_step=10)
        return EngineJobStatus(state="succeeded", progress=1.0, stage="save_image")

    async def fake_outputs(self, engine_job_id):
        return [EngineOutputFile(filename=f"{engine_job_id}.png", data=PNG_FIXTURE)]

    monkeypatch.setattr(MockEngineAdapter, "get_job_status", fake_status)
    monkeypatch.setattr(MockEngineAdapter, "get_job_outputs", fake_outputs)

    app_settings = dataclasses.replace(
        settings,
        workflow=WorkflowConfig(raw={"engine": {"provider": "mock", "options": {
            "worker_poll_interval_ms": 10, "engine_poll_ms": 10,
        }}}),
    )
    capture = _CaptureBroker()
    app = create_app(app_settings)
    original_broker = job_service._EVENT_BROKER
    try:
        with TestClient(app) as client:
            # lifespan 启动会用真实 broker 重置一次，必须在进入上下文后再替换
            job_service.set_event_broker(capture)
            job = client.post("/api/v1/jobs", json={"snapshot": make_snapshot(1)}).json()
            deadline = time.monotonic() + 20
            final = None
            while time.monotonic() < deadline:
                final = client.get(f"/api/v1/jobs/{job['id']}").json()
                if final["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
                    break
                time.sleep(0.05)
            assert final["status"] == "COMPLETED", final
    finally:
        job_service.set_event_broker(original_broker)

    # SSE 实时层：必须广播过带 step 的 ITEM_PROGRESS
    progress_events = [e for e in capture.events if e["type"] == "ITEM_PROGRESS"]
    assert progress_events, "采样过程必须广播 ITEM_PROGRESS 临时事件"
    assert any(e["payload"].get("step") is not None for e in progress_events)

    # 持久层：job_events 中零 ITEM_PROGRESS 行
    engine = make_engine(settings.storage.database_path)
    try:
        from sqlalchemy.orm import Session
        with Session(engine) as session:
            assert session.query(JobEvent).filter_by(event_type="ITEM_PROGRESS").count() == 0
    finally:
        engine.dispose()
