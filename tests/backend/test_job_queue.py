"""Phase 2A Job/Queue 执行核心测试（规范 §五十八 清单）。

通过 TestClient 驱动真实 lifespan（Worker 为 asyncio 任务），
用 MockEngineAdapter 注入各种故障模式。
"""
from __future__ import annotations

import dataclasses
import json
import time

import pytest

from app.core.config import Settings, WorkflowConfig
from app.main import create_app


def mock_settings(settings: Settings, **options) -> Settings:
    """注入 MockEngine 行为选项（短轮询间隔，加速测试）。"""
    merged = {"worker_poll_interval_ms": 30, "engine_poll_ms": 20}
    merged.update(options)
    return dataclasses.replace(
        settings,
        workflow=WorkflowConfig(raw={"engine": {"provider": "mock", "options": merged}}),
    )


def wait_for(client, job_id, predicate, timeout=15.0):
    """轮询任务状态直到满足条件（SSE 之外的事实源：DB 状态）。"""
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


def test_job_lifecycle_serial_completion(mock_client):
    """8 张任务正常串行：逐张完成、completed_count 递增、每张 Seed 独立。"""
    response = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=8)})
    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "QUEUED" and len(job["items"]) == 8
    assert job["provider"] == "mock" and job["module_id"] == "basic_generate"

    final = wait_for(mock_client, job["id"], lambda j: j["status"] in ("COMPLETED", "FAILED"), timeout=30)
    assert final["status"] == "COMPLETED"
    assert final["completed_count"] == 8
    seeds = {item["seed"] for item in final["items"] if item["status"] == "COMPLETED"}
    assert len(seeds) == 8, "每张图必须独立随机 Seed"
    assert all(item["seed"] is not None for item in final["items"])


def test_pause_at_item_boundary(mock_client):
    """暂停发生在 Item 边界：当前 Item 完成后 Job → PAUSED，已完成的不重跑。"""
    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=6)}).json()
    wait_for(mock_client, job["id"], lambda j: j["status"] == "RUNNING" and j["completed_count"] >= 1)
    mock_client.post(f"/api/v1/jobs/{job['id']}/pause")

    paused = wait_for(mock_client, job["id"], lambda j: j["status"] == "PAUSED")
    completed_before = paused["completed_count"]
    assert 1 <= completed_before < 6
    running_items = [i for i in paused["items"] if i["status"] == "RUNNING"]
    assert running_items == [], "暂停后不应有 RUNNING Item"

    # 继续：PAUSED → QUEUED → RUNNING → COMPLETED，已完成 Item 不重跑（seed 不变）
    seeds_before = {i["item_index"]: i["seed"] for i in paused["items"] if i["status"] == "COMPLETED"}
    mock_client.post(f"/api/v1/jobs/{job['id']}/resume")
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED", timeout=30)
    seeds_after = {i["item_index"]: i["seed"] for i in final["items"] if i["status"] == "COMPLETED"}
    assert all(seeds_after[idx] == seed for idx, seed in seeds_before.items()), "已完成 Item 绝不重新执行"
    assert final["completed_count"] == 6


def test_cancel_keeps_completed_images(mock_client):
    """取消保留完成图片；Job 终态 CANCELLED；不可再 RUNNING。"""
    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=8)}).json()
    wait_for(mock_client, job["id"], lambda j: j["status"] == "RUNNING" and j["completed_count"] >= 1)
    mock_client.post(f"/api/v1/jobs/{job['id']}/cancel")

    cancelled = wait_for(mock_client, job["id"], lambda j: j["status"] == "CANCELLED")
    assert cancelled["completed_count"] >= 1
    completed_items = [i for i in cancelled["items"] if i["status"] == "COMPLETED"]
    assert len(completed_items) == cancelled["completed_count"]
    # CANCELLED → 禁止再 RUNNING：继续操作应被拒绝
    assert mock_client.post(f"/api/v1/jobs/{job['id']}/resume").status_code == 400


def test_cancel_then_resume_creates_child_job(mock_client):
    """取消后 resume-remaining：创建子 Job（resume_of_job_id），只含剩余数量。"""
    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=6)}).json()
    wait_for(mock_client, job["id"], lambda j: j["status"] == "RUNNING" and j["completed_count"] >= 2)
    mock_client.post(f"/api/v1/jobs/{job['id']}/cancel")
    cancelled = wait_for(mock_client, job["id"], lambda j: j["status"] == "CANCELLED")

    child_response = mock_client.post(f"/api/v1/jobs/{job['id']}/resume-remaining")
    assert child_response.status_code == 201
    child = child_response.json()
    assert child["resume_of_job_id"] == job["id"]
    assert child["source"] == "resume"
    assert child["requested_count"] == 6 - cancelled["completed_count"]
    assert len(child["items"]) == child["requested_count"]

    final = wait_for(mock_client, child["id"], lambda j: j["status"] == "COMPLETED", timeout=30)
    assert final["completed_count"] == child["requested_count"]
    # 新 Item 使用新随机 Seed（规范 §二十/§九）
    parent_seeds = {i["seed"] for i in cancelled["items"] if i["seed"] is not None}
    child_seeds = {i["seed"] for i in final["items"]}
    assert not (parent_seeds & child_seeds), "续跑应使用新随机 Seed"


def test_priority_next_inserts_after_running(mock_client):
    """优先任务只插到当前 Job 后（规范 §十五）：B C 等待中，next X → X B C。"""
    first = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1)}).json()
    b = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1)}).json()
    c = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1)}).json()
    wait_for(mock_client, first["id"], lambda j: j["status"] == "RUNNING")
    x = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1), "queue_mode": "next"}).json()
    queue = mock_client.get("/api/v1/queue").json()
    queued_ids = [j["id"] for j in queue["queued"]]
    assert queued_ids == [x["id"], b["id"], c["id"]]
    assert queue["running"]["id"] == first["id"]


def test_queue_reorder(mock_client):
    """多个等待任务拖拽排序：仅 QUEUED 可排序。"""
    holder = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1)}).json()
    wait_for(mock_client, holder["id"], lambda j: j["status"] == "RUNNING")
    a = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1)}).json()
    b = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1)}).json()
    c = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1)}).json()

    reordered = mock_client.post("/api/v1/queue/reorder",
                                 json={"ordered_job_ids": [c["id"], a["id"], b["id"]]}).json()
    assert [j["id"] for j in reordered["queued"]] == [c["id"], a["id"], b["id"]]

    # RUNNING 不在排序列表里 → 请求被拒绝
    bad = mock_client.post("/api/v1/queue/reorder",
                           json={"ordered_job_ids": [holder["id"], a["id"], b["id"]]})
    assert bad.status_code == 400


def test_engine_offline_systemic_failure_pauses_queue(mock_client):
    """引擎离线：Job FAILED + 队列自动暂停，不烧完后续队列（规范 §二十一）。"""
    holder = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1)}).json()
    wait_for(mock_client, holder["id"], lambda j: j["status"] == "COMPLETED")

    adapter = mock_client.app.state.adapter
    adapter.mode = "offline"
    try:
        offline = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=2)}).json()
        follower = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1)}).json()
        failed = wait_for(mock_client, offline["id"], lambda j: j["status"] == "FAILED", timeout=30)
        assert failed["error_type"] == "ENGINE_OFFLINE"
        queue = mock_client.get("/api/v1/queue").json()
        assert queue["worker"]["queue_paused"] is True
        time.sleep(1.0)
        assert mock_client.get(f"/api/v1/jobs/{follower['id']}").json()["status"] == "QUEUED", \
            "队列暂停后不得继续执行后续任务"
    finally:
        adapter.mode = "success"

    # 用户处理故障后恢复队列 → follower 执行
    mock_client.post("/api/v1/queue/resume")
    wait_for(mock_client, follower["id"], lambda j: j["status"] == "COMPLETED", timeout=30)


def test_oom_failure_no_retry(mock_client):
    """OOM：Item FAILED(OUT_OF_MEMORY)，不自动重试，Job FAILED。"""
    adapter = mock_client.app.state.adapter
    adapter.mode = "oom"  # 提交前注入（避免竞态）
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1)}).json()
        final = wait_for(mock_client, job["id"], lambda j: j["status"] == "FAILED", timeout=30)
        failed_items = [i for i in final["items"] if i["status"] == "FAILED"]
        assert failed_items and failed_items[0]["error_type"] == "OUT_OF_MEMORY"
        assert failed_items[0]["retry_count"] == 0, "OOM 不自动重试"
        assert mock_client.get("/api/v1/queue").json()["worker"]["queue_paused"] is True
    finally:
        adapter.mode = "success"
        mock_client.post("/api/v1/queue/resume")


def test_workflow_error_no_retry_pauses_queue(mock_client):
    """Workflow / 节点错误：Item FAILED（保留分类），不自动重试，Job FAILED + 队列暂停。"""
    adapter = mock_client.app.state.adapter
    adapter.mode = "workflow_error"  # 提交前注入（避免竞态）
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1)}).json()
        final = wait_for(mock_client, job["id"], lambda j: j["status"] == "FAILED", timeout=30)
        failed_items = [i for i in final["items"] if i["status"] == "FAILED"]
        assert failed_items, "workflow 错误必须让 Item FAILED"
        assert failed_items[0]["error_type"] in ("WORKFLOW_ERROR", "NODE_MISSING")
        assert failed_items[0]["retry_count"] == 0, "Workflow 错误不自动重试"
        assert mock_client.get("/api/v1/queue").json()["worker"]["queue_paused"] is True
    finally:
        adapter.mode = "success"
        mock_client.post("/api/v1/queue/resume")


def test_transient_network_retry_then_success(mock_client):
    """网络断开恢复：前 2 次提交瞬态失败 → 自动重试 ≤2 后成功，任务正常完成（§三十六）。"""
    adapter = mock_client.app.state.adapter
    adapter.transient_fail_times = 2
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=1)}).json()
        final = wait_for(mock_client, job["id"], lambda j: j["status"] in ("COMPLETED", "FAILED"), timeout=30)
        assert final["status"] == "COMPLETED", "瞬态网络错误必须自动重试并恢复"
    finally:
        adapter.transient_fail_times = 0


def test_client_request_id_idempotency(mock_client):
    """client_request_id 重复请求不重复创建（规范 §十二）。"""
    body = {"snapshot": make_snapshot(count=2), "client_request_id": "req-001"}
    first = mock_client.post("/api/v1/jobs", json=body).json()
    second = mock_client.post("/api/v1/jobs", json=body).json()
    assert first["id"] == second["id"]
    assert second.get("idempotent_replay") is True
    # 相同 request id 但来源不同 → 各自独立
    agent_body = {"snapshot": make_snapshot(count=2), "client_request_id": "req-001", "source": "agent"}
    third = mock_client.post("/api/v1/jobs", json=agent_body).json()
    assert third["id"] != first["id"]


def test_startup_recovers_running_to_interrupted(settings, png_bytes):
    """应用重启发现 RUNNING → INTERRUPTED（规范 §三十七），不自动重新排队。"""
    from fastapi.testclient import TestClient

    app = create_app(mock_settings(settings))
    with TestClient(app) as client:
        job = client.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=3)}).json()
        wait_for(client, job["id"], lambda j: j["status"] == "RUNNING")
        job_id = job["id"]
        engine = client.app.state.engine
    # 模拟崩溃：进程直接结束（未等 Worker 收尾），数据库中 Job 停在 RUNNING/部分完成
    engine.dispose()

    # 重启：新 app 实例（lifespan 恢复逻辑）
    app2 = create_app(mock_settings(settings))
    with TestClient(app2) as client2:
        recovered = wait_for(client2, job_id, lambda j: j["status"] != "RUNNING", timeout=10)
        assert recovered["status"] in ("INTERRUPTED", "PAUSED", "COMPLETED")
        if recovered["status"] == "INTERRUPTED":
            running_items = [i for i in recovered["items"] if i["status"] == "RUNNING"]
            assert running_items == []
            # 续跑剩余 → 子 Job 完成
            child = client2.post(f"/api/v1/jobs/{job_id}/resume-remaining").json()
            wait_for(client2, child["id"], lambda j: j["status"] == "COMPLETED", timeout=30)


def test_sse_stream_receives_events(settings):
    """SSE：真实 HTTP 流可收到事件；重连后重新 GET（DB 为事实源）。"""
    import httpx
    import threading
    import uvicorn

    app = create_app(mock_settings(settings))
    config = uvicorn.Config(app, host="127.0.0.1", port=18899, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not server.started:
        time.sleep(0.05)
    assert server.started, "测试服务器未启动"

    try:
        events: list[str] = []
        job_id_holder: list[str] = []

        def consume():
            with httpx.Client(timeout=20, trust_env=False) as http:
                with http.stream("GET", "http://127.0.0.1:18899/api/v1/events/jobs") as response:
                    for line in response.iter_lines():
                        if line.startswith("data:") and job_id_holder:
                            events.append(line)
                            if job_id_holder[0] in line:
                                return

        consumer = threading.Thread(target=consume, daemon=True)
        consumer.start()
        time.sleep(0.5)

        with httpx.Client(timeout=20, trust_env=False) as http:
            created = http.post("http://127.0.0.1:18899/api/v1/jobs",
                                json={"snapshot": make_snapshot(count=1)}).json()
            job_id_holder.append(created["id"])
        consumer.join(timeout=15)
        assert events and any(job_id_holder[0] in event for event in events), "SSE 应收到该任务事件"

        # 重连后重新 GET（数据库为唯一事实源）
        with httpx.Client(timeout=20, trust_env=False) as http:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                final = http.get(f"http://127.0.0.1:18899/api/v1/jobs/{job_id_holder[0]}").json()
                if final["status"] == "COMPLETED":
                    break
                time.sleep(0.1)
            assert final["status"] == "COMPLETED"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_seed_fixed_mode_single_image_only(mock_client):
    """§0.4：固定 Seed 仅用于单张精确复现；count>1 必须拒绝（禁止 base_seed+index）。"""
    rejected = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(count=3, seed_mode="fixed", seed=12345),
    })
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "FIXED_SEED_SINGLE_ONLY"

    job = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(count=1, seed_mode="fixed", seed=12345),
    }).json()
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED", timeout=30)
    assert [i["seed"] for i in final["items"]] == [12345]
