"""§十：队列全局安全暂停 / 继续测试。

复用 test_job_queue.py 的 mock_settings / wait_for / make_snapshot 夹具风格。
覆盖：
- POST /queue/pause 后 worker.queue_paused=true，running job 的 pause_requested 被置位；
- 暂停期间 worker 不派发新 QUEUED 任务；running job 在安全边界转 PAUSED；
- POST /queue/resume 清除 flag，被暂停 job 以 queue_position=0 排首恢复、优先执行；
- 暂停/继续幂等，不产生新状态。
"""
from __future__ import annotations

import dataclasses
import json
import time

import pytest

from app.core.config import Settings, WorkflowConfig
from app.main import create_app


def mock_settings(settings: Settings, **options) -> Settings:
    merged = {"worker_poll_interval_ms": 30, "engine_poll_ms": 20}
    merged.update(options)
    return dataclasses.replace(
        settings,
        workflow=WorkflowConfig(raw={"engine": {"provider": "mock", "options": merged}}),
    )


def wait_for(client, job_id, predicate, timeout=15.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        last = response.json()
        if predicate(last):
            return last
        time.sleep(0.05)
    raise AssertionError(f"等待任务状态超时: {json.dumps(last, ensure_ascii=False)[:400]}")


def make_snapshot(count=4, **overrides):
    snapshot = {
        "prompt_mode": "structured",
        "structured_prompt": {"style": "anime", "face": "侧脸", "scene": "cafe"},
        "full_prompt": "",
        "negative_prompt": "blurry",
        "selected_assets": {},
        "width": 512, "height": 768,
        "count": count,
        "seed_mode": "random",
        "workflow_modules": [],
    }
    snapshot.update(overrides)
    return snapshot


@pytest.fixture()
def mock_client(settings):
    app = create_app(mock_settings(settings))
    with __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app) as test_client:
        yield test_client


def test_global_pause_sets_flag_and_pause_requested(mock_client):
    """POST /queue/pause → worker.queue_paused=true，running job 的 pause_requested 置位。"""
    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=4)}).json()
    wait_for(mock_client, job["id"], lambda j: j["status"] == "RUNNING" and j["completed_count"] >= 1)

    resp = mock_client.post("/api/v1/queue/pause")
    assert resp.status_code == 200
    queue = resp.json()
    assert queue["worker"]["queue_paused"] is True
    assert queue["worker"]["queue_paused_reason"] == "USER_REQUEST"

    # running job 的 pause_requested 应被置位（worker 边界会落 PAUSED）
    running = mock_client.get(f"/api/v1/jobs/{job['id']}").json()
    assert running["pause_requested"] is True


def test_pause_stops_dispatching_and_job_pauses_at_boundary(mock_client):
    """暂停期间不派发新 QUEUED 任务；running job 在安全边界转 PAUSED。"""
    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=4)}).json()
    wait_for(mock_client, job["id"], lambda j: j["status"] == "RUNNING" and j["completed_count"] >= 1)

    # 先入队一个后续任务
    follower = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1)}).json()

    mock_client.post("/api/v1/queue/pause")

    # running job 在边界转 PAUSED
    paused = wait_for(mock_client, job["id"], lambda j: j["status"] == "PAUSED")
    assert 1 <= paused["completed_count"] < 4

    # 暂停期间 follower 保持 QUEUED，不被派发
    time.sleep(0.5)
    follower_state = mock_client.get(f"/api/v1/jobs/{follower['id']}").json()
    assert follower_state["status"] == "QUEUED", "队列暂停后不得派发后续任务"

    queue = mock_client.get("/api/v1/queue").json()
    assert queue["worker"]["queue_paused"] is True
    assert [j["id"] for j in queue["queued"]] == [follower["id"]]
    assert [j["id"] for j in queue["paused"]] == [job["id"]]


def test_resume_restores_paused_job_to_front(mock_client):
    """POST /queue/resume 清 flag；被暂停 job 排队首（queue_position=0），优先于 follower 执行。"""
    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=4)}).json()
    wait_for(mock_client, job["id"], lambda j: j["status"] == "RUNNING" and j["completed_count"] >= 1)
    follower = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1)}).json()

    mock_client.post("/api/v1/queue/pause")
    wait_for(mock_client, job["id"], lambda j: j["status"] == "PAUSED")

    # 确认 follower 已 QUEUED、job 已 PAUSED
    queue_before = mock_client.get("/api/v1/queue").json()
    assert queue_before["worker"]["queue_paused"] is True
    assert [j["id"] for j in queue_before["queued"]] == [follower["id"]]

    # 恢复队列
    resp = mock_client.post("/api/v1/queue/resume")
    assert resp.status_code == 200
    queue = resp.json()
    assert queue["worker"]["queue_paused"] is False

    # 被暂停 job 应排到队首（在 follower 之前）
    queued_ids = [j["id"] for j in queue["queued"]]
    assert job["id"] in queued_ids, "被暂停 job 应回到 QUEUED"
    assert queued_ids[0] == job["id"], "被暂停 job 必须排队首（先于 follower）"
    assert queued_ids[1] == follower["id"] if len(queued_ids) > 1 else True

    # pause_requested 已清空
    resumed_job = next(j for j in queue["queued"] if j["id"] == job["id"])
    assert resumed_job["pause_requested"] is False

    # 被暂停 job 优先执行：先完成的应是它（而非 follower）
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED", timeout=30)
    assert final["status"] == "COMPLETED"
    assert final["completed_count"] == 4

    # follower 随后也完成
    wait_for(mock_client, follower["id"], lambda j: j["status"] == "COMPLETED", timeout=30)


def test_pause_resume_idempotent(mock_client):
    """连续调用 pause / resume 幂等，不产生新状态、不报错。"""
    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=2)}).json()
    wait_for(mock_client, job["id"], lambda j: j["status"] == "RUNNING")

    # 连续 pause 两次
    r1 = mock_client.post("/api/v1/queue/pause")
    r2 = mock_client.post("/api/v1/queue/pause")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["worker"]["queue_paused"] is True

    # 等待 paused
    wait_for(mock_client, job["id"], lambda j: j["status"] == "PAUSED")

    # 连续 resume 两次
    r3 = mock_client.post("/api/v1/queue/resume")
    r4 = mock_client.post("/api/v1/queue/resume")
    assert r3.status_code == 200 and r4.status_code == 200
    assert r4.json()["worker"]["queue_paused"] is False

    # job 最终能完成（不产生 INTERRUPTED / FAILED）
    final = wait_for(mock_client, job["id"], lambda j: j["status"] in ("COMPLETED", "FAILED"), timeout=30)
    assert final["status"] == "COMPLETED"


def test_pause_without_running_job_only_sets_flag(mock_client):
    """暂停瞬间无 RUNNING job（空队列）：resume 仅清 flag，不报错。"""
    # 队列空时直接 pause
    resp = mock_client.post("/api/v1/queue/pause")
    assert resp.status_code == 200
    assert resp.json()["worker"]["queue_paused"] is True

    # resume 正常清 flag
    resp2 = mock_client.post("/api/v1/queue/resume")
    assert resp2.status_code == 200
    assert resp2.json()["worker"]["queue_paused"] is False

    # 之后正常提交任务不受影响
    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1)}).json()
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED", timeout=30)
    assert final["status"] == "COMPLETED"
