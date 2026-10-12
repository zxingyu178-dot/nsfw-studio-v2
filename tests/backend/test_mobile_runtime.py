"""MobileReviewRuntimeService 测试（全部 monkeypatch seam，绝不起真实进程）。"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.services.mobile_review_runtime_service import (
    BridgeNotOwned,
    BridgePortConflict,
    MobileReviewRuntimeService,
)


def _make_service(tmp_path: Path, **overrides) -> MobileReviewRuntimeService:
    settings = SimpleNamespace(
        storage=SimpleNamespace(data_root=tmp_path / "data"),
        mobile_review={"enabled": True, "host": "127.0.0.1", "port": 8767, **overrides},
    )
    return MobileReviewRuntimeService(settings)


def _healthy_probe():
    return {"product": "nsfw-studio", "status": "ok", "version": "0.13.0"}


def test_start_success(tmp_path, monkeypatch):
    svc = _make_service(tmp_path)
    spawned: list[int] = []

    def fake_spawn():
        pid = 87671
        spawned.append(pid)
        svc._parent_pid = 42  # 真实 _spawn 会设置父 PID（orphan 防护）
        return pid

    monkeypatch.setattr(svc, "_spawn", fake_spawn)
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(svc, "_probe",
                        lambda: None if svc._pid is None else _healthy_probe())
    terminated: list[int] = []
    monkeypatch.setattr(svc, "_terminate_tree", lambda pid: terminated.append(pid))

    snap = svc.start()
    assert spawned == [87671]
    assert snap.state == "RUNNING"
    assert snap.owned is True
    assert snap.pid == 87671
    assert snap.parent_pid == 42  # orphan 防护记录父 PID
    assert terminated == []


def test_start_idempotent(tmp_path, monkeypatch):
    svc = _make_service(tmp_path)
    spawned: list[int] = []

    def fake_spawn():
        spawned.append(1)
        svc._parent_pid = 42
        return 1

    monkeypatch.setattr(svc, "_spawn", fake_spawn)
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(svc, "_probe",
                        lambda: None if svc._pid is None else _healthy_probe())
    monkeypatch.setattr(svc, "_terminate_tree", lambda pid: None)

    svc.start()
    svc.start()
    assert len(spawned) == 1  # 幂等，不起第二个进程


def test_port_conflict(tmp_path, monkeypatch):
    svc = _make_service(tmp_path)
    monkeypatch.setattr(svc, "_probe", lambda: {"responded": True})  # 有响应但不是 Bridge
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: False)
    try:
        svc.start()
        assert False, "应抛 BridgePortConflict"
    except BridgePortConflict:
        pass


def test_stop_only_owned(tmp_path, monkeypatch):
    svc = _make_service(tmp_path)
    monkeypatch.setattr(svc, "_spawn", lambda: 4242)
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(svc, "_probe",
                        lambda: None if svc._pid is None else _healthy_probe())
    terminated: list[int] = []
    monkeypatch.setattr(svc, "_terminate_tree", lambda pid: terminated.append(pid))

    svc.start()
    snap = svc.stop()
    assert terminated == [4242]  # 只停自己启动的 PID
    assert snap.state == "STOPPED"


def test_stop_unowned_port_conflict_raises(tmp_path, monkeypatch):
    svc = _make_service(tmp_path)
    monkeypatch.setattr(svc, "_probe", lambda: {"responded": True})
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: False)
    try:
        svc.stop()
        assert False, "外部占用应拒绝停止"
    except BridgeNotOwned:
        pass
