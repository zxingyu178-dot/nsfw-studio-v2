"""受管 ComfyUI 运行时服务测试（Commit 3）。

全部用 monkeypatch 替换 spawn/probe/pid_alive/terminate 四个 seam：
绝不起真实 ComfyUI、绝不碰真实进程。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import engine_runtime_service as svc_mod
from app.services.engine_runtime_service import (
    EngineNotOwned,
    EnginePortConflict,
    EngineRuntimeService,
    _Probe,
)


def _make_service(tmp_path: Path, **rt_overrides) -> EngineRuntimeService:
    settings = SimpleNamespace(
        storage=SimpleNamespace(data_root=tmp_path / "data"),
        engine_runtime={
            "managed": True,
            "python_exe": "py",
            "working_dir": "C:/fake/comfyui",
            "entrypoint": "main.py",
            **rt_overrides,
        },
    )
    return EngineRuntimeService(settings)


def test_managed_start_success(tmp_path, monkeypatch):
    svc = _make_service(tmp_path)
    spawned: list[int] = []

    monkeypatch.setattr(svc, "_spawn", lambda: spawned.append(9999) or 9999)
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: True)

    def probe():
        # 未 spawn 前端口关闭；spawn 后变为健康 ComfyUI
        if svc._pid is None:
            return _Probe(online=False, responded=False)
        return _Probe(online=True, responded=True, version="0.3.1")

    monkeypatch.setattr(svc, "_probe", probe)
    terminated: list[int] = []
    monkeypatch.setattr(svc, "_terminate_tree", lambda pid: terminated.append(pid))

    snap = svc.start()

    assert len(spawned) == 1
    assert snap.state == "RUNNING_MANAGED"
    assert snap.owned is True
    assert snap.pid == 9999
    assert snap.health["online"] is True
    assert snap.health["engine_version"] == "0.3.1"
    assert snap.started_at is not None
    assert terminated == []  # 启动成功不应清理


def test_external_detect(tmp_path, monkeypatch):
    svc = _make_service(tmp_path)
    monkeypatch.setattr(svc, "_probe", lambda: _Probe(online=True, responded=True, version="0.3.0"))
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: False)

    snap = svc.status()
    assert snap.state == "RUNNING_EXTERNAL"
    assert snap.owned is False
    assert snap.pid is None


def test_port_conflict(tmp_path, monkeypatch):
    svc = _make_service(tmp_path)
    # 端口有响应但不是 ComfyUI
    monkeypatch.setattr(svc, "_probe", lambda: _Probe(online=False, responded=True))
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: False)

    snap = svc.status()
    assert snap.state == "PORT_CONFLICT"
    assert snap.owned is False

    # start 在 PORT_CONFLICT 下应抛 409
    with pytest.raises(EnginePortConflict):
        svc.start()


def test_owned_stop_only_terminates_managed_tree(tmp_path, monkeypatch):
    svc = _make_service(tmp_path)
    monkeypatch.setattr(svc, "_spawn", lambda: 7777)
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: True)

    def probe():
        if svc._pid is None:
            return _Probe(online=False, responded=False)
        return _Probe(online=True, responded=True, version="1.0")

    monkeypatch.setattr(svc, "_probe", probe)
    terminated: list[int] = []
    monkeypatch.setattr(svc, "_terminate_tree", lambda pid: terminated.append(pid))

    svc.start()
    terminated.clear()

    snap = svc.stop()
    assert terminated == [7777]  # 只终止受管 PID 树
    assert snap.state == "STOPPED"
    assert snap.pid is None
    assert svc._pid is None


def test_cannot_kill_external(tmp_path, monkeypatch):
    svc = _make_service(tmp_path)
    monkeypatch.setattr(svc, "_probe", lambda: _Probe(online=True, responded=True, version="0.3.0"))
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: False)
    terminated: list[int] = []
    monkeypatch.setattr(svc, "_terminate_tree", lambda pid: terminated.append(pid))

    with pytest.raises(EngineNotOwned):
        svc.stop()
    assert terminated == []  # external 绝不被终止


def test_idempotent_start_no_double_spawn(tmp_path, monkeypatch):
    svc = _make_service(tmp_path)
    spawned: list[int] = []
    monkeypatch.setattr(svc, "_spawn", lambda: spawned.append(5555) or 5555)
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: True)

    def probe():
        if svc._pid is None:
            return _Probe(online=False, responded=False)
        return _Probe(online=True, responded=True, version="1.0")

    monkeypatch.setattr(svc, "_probe", probe)
    monkeypatch.setattr(svc, "_terminate_tree", lambda pid: None)

    first = svc.start()
    second = svc.start()  # 第二次：幂等，不得再起进程

    assert first.state == "RUNNING_MANAGED"
    assert second.state == "RUNNING_MANAGED"
    assert len(spawned) == 1
