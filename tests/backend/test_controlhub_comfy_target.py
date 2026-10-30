"""ControlHub 适配器把 engine start/stop/status/restart 委托给 CLI（id=comfyui）。

全部 mock ``_run`` seam（绝不真实起进程），验证：
- 每次调用 argv 正确且 integration_id 恒为 comfyui（绝不 nsfw-studio-v2）；
- CLI JSON / 退出码 → 前端冻结状态语义的映射：
  succeeded / blocked / port_conflict / timed_out / 未批准(exit 2)。
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.engine_runtime_service import (
    ControlHubEngineRuntime,
    EnginePortConflict,
)


def _make(tmp_path: Path) -> ControlHubEngineRuntime:
    settings = SimpleNamespace(
        storage=SimpleNamespace(data_root=tmp_path / "data"),
        engine_runtime={"host": "127.0.0.1", "port": 8188},
        controlhub={},
    )
    return ControlHubEngineRuntime(settings)


def _fake_run(responses: dict[str, tuple[int, str]], calls: list[list[str]]):
    """返回一个 _run 替身：按 argv[3](action) 查表返回 (exit, stdout)，并记录 argv。"""

    def _run(argv: list[str]) -> tuple[int, str]:
        calls.append(argv)
        action = argv[3]
        exit_code, out = responses.get(action, (0, "{}"))
        return exit_code, out

    return _run


def _json(**kw) -> str:
    return json.dumps(kw)


def test_status_online_maps_to_running_managed(tmp_path, monkeypatch):
    svc = _make(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        svc._client, "_run",
        _fake_run({"status": (0, _json(state="online"))}, calls),
    )
    snap = svc.status()
    assert snap.state == "RUNNING_MANAGED"
    assert snap.owned is True
    assert snap.health["online"] is True


def test_status_offline_maps_to_stopped(tmp_path, monkeypatch):
    svc = _make(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        svc._client, "_run",
        _fake_run({"status": (0, _json(state="offline"))}, calls),
    )
    snap = svc.status()
    assert snap.state == "STOPPED"
    assert snap.owned is False


def test_status_degraded_maps_to_running_managed(tmp_path, monkeypatch):
    svc = _make(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        svc._client, "_run",
        _fake_run({"status": (0, _json(state="degraded"))}, calls),
    )
    snap = svc.status()
    assert snap.state == "RUNNING_MANAGED"


def test_start_succeeded_then_status_online(tmp_path, monkeypatch):
    svc = _make(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        svc._client, "_run",
        _fake_run({
            "start": (0, _json(state="succeeded", reason="already_in_target_state")),
            "status": (0, _json(state="online")),
        }, calls),
    )
    snap = svc.start()
    assert snap.state == "RUNNING_MANAGED"
    # 先 start 后 status
    assert calls[0][3] == "start"
    assert calls[1][3] == "status"
    # 全部调用 integration_id = comfyui
    for argv in calls:
        assert argv[4] == "comfyui"
        assert "nsfw-studio-v2" not in argv


def test_start_port_conflict_raises_engine_port_conflict(tmp_path, monkeypatch):
    svc = _make(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        svc._client, "_run",
        _fake_run({"start": (1, _json(state="blocked", reason="port_conflict"))}, calls),
    )
    with pytest.raises(EnginePortConflict):
        svc.start()


def test_start_blocked_maps_to_error(tmp_path, monkeypatch):
    svc = _make(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        svc._client, "_run",
        _fake_run({"start": (1, _json(state="blocked", reason="dependency_missing"))}, calls),
    )
    snap = svc.start()
    assert snap.state == "ERROR"


def test_start_timed_out_maps_to_starting(tmp_path, monkeypatch):
    svc = _make(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        svc._client, "_run",
        _fake_run({"start": (1, _json(state="timed_out"))}, calls),
    )
    snap = svc.start()
    assert snap.state == "STARTING"


def test_start_unapproved_exit2_maps_to_error(tmp_path, monkeypatch):
    svc = _make(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        svc._client, "_run",
        _fake_run({"start": (2, _json(state="failed", reason="unknown_integration"))}, calls),
    )
    snap = svc.start()
    assert snap.state == "ERROR"
    assert "未注册" in snap.detail or "未批准" in snap.detail


def test_stop_succeeded_maps_to_stopped(tmp_path, monkeypatch):
    svc = _make(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        svc._client, "_run",
        _fake_run({"stop": (0, _json(state="succeeded", reason="completed"))}, calls),
    )
    snap = svc.stop()
    assert snap.state == "STOPPED"
    assert calls[0][3] == "stop"
    assert calls[0][4] == "comfyui"


def test_stop_unapproved_is_idempotent_stopped(tmp_path, monkeypatch):
    svc = _make(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        svc._client, "_run",
        _fake_run({"stop": (2, _json(state="failed", reason="unknown_integration"))}, calls),
    )
    snap = svc.stop()
    assert snap.state == "STOPPED"  # 未注册 → 视为已停（幂等），不报错


def test_restart_succeeded(tmp_path, monkeypatch):
    svc = _make(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        svc._client, "_run",
        _fake_run({
            "restart": (0, _json(state="succeeded")),
            "status": (0, _json(state="online")),
        }, calls),
    )
    snap = svc.restart()
    assert snap.state == "RUNNING_MANAGED"
    assert calls[0][3] == "restart"


def test_status_snapshot_has_short_ttl(tmp_path, monkeypatch):
    from app.services import engine_runtime_service as module
    now = [0.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: now[0])
    svc = _make(tmp_path)
    calls = []
    monkeypatch.setattr(svc._client, '_run', _fake_run({'status': (0, _json(state='online'))}, calls))
    svc.status()
    now[0] = 2.9
    svc.status()
    assert len(calls) == 1
    now[0] = 3.1
    svc.status()
    assert len(calls) == 2


def test_concurrent_status_queries_share_one_cli_process(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    svc = _make(tmp_path)
    entered, release = Event(), Event()
    calls = []
    def run(argv):
        calls.append(argv)
        entered.set()
        assert release.wait(3)
        return 0, _json(state='online')
    monkeypatch.setattr(svc._client, '_run', run)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(svc.status) for _ in range(4)]
        assert entered.wait(3)
        release.set()
        assert all(f.result(timeout=5).state == 'RUNNING_MANAGED' for f in futures)
    assert len(calls) == 1


def test_actions_invalidate_status_but_are_never_cached(tmp_path, monkeypatch):
    svc = _make(tmp_path)
    calls = []
    online = [False]
    def run(argv):
        action = argv[3]
        calls.append(action)
        if action == 'status':
            return 0, _json(state='online' if online[0] else 'offline')
        online[0] = action == 'start'
        return 0, _json(state='succeeded')
    monkeypatch.setattr(svc._client, '_run', run)
    assert svc.status().state == 'STOPPED'
    assert svc.start().state == 'RUNNING_MANAGED'
    svc.stop()
    assert svc.status().state == 'STOPPED'
    svc.stop()
    assert calls.count('stop') == 2
    assert calls.count('start') == 1
