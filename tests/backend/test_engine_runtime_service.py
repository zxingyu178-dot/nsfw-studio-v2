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


def test_default_health_timeout_is_300(tmp_path):
    """健康等待上限默认为 300s（v0.13.2：覆盖慢冷启 + uv re-exec，真机约 3 分钟）。"""
    svc = _make_service(tmp_path)
    assert svc.health_timeout == 300.0


def test_health_timeout_is_configurable(tmp_path):
    """可通过 engine_runtime.health_timeout_seconds 覆盖默认值。"""
    svc = _make_service(tmp_path, health_timeout_seconds=7.5)
    assert svc.health_timeout == 7.5


def test_start_times_out_after_configurable_health_timeout(tmp_path, monkeypatch):
    """探针始终离线时，start() 应在“可配置的”健康等待上限后判 ERROR，并清理自己起的进程树。

    把 health_timeout_seconds 设得很小：start() 必须在远小于旧写死 60s 的时间内返回 ERROR，
    证明截止时间已由配置决定（不再写死 60）。
    """
    import time

    svc = _make_service(tmp_path, health_timeout_seconds=0.2)
    spawned: list[int] = []
    monkeypatch.setattr(svc, "_spawn", lambda: spawned.append(4242) or 4242)
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: True)
    # 始终离线：永远不会健康
    monkeypatch.setattr(svc, "_probe", lambda: _Probe(online=False, responded=False))
    terminated: list[int] = []
    monkeypatch.setattr(svc, "_terminate_tree", lambda pid: terminated.append(pid))

    t0 = time.monotonic()
    snap = svc.start()
    elapsed = time.monotonic() - t0

    assert len(spawned) == 1            # 确实拉起了受管进程
    assert snap.state == "ERROR"        # 超时判失败
    assert terminated == [4242]        # 清理自己刚启动的进程树（不留孤儿）
    assert svc._pid is None
    # 关键：可配置小超时生效，远小于历史写死的 60s（轮询间隔 1s，故这里 ~1s 量级）
    assert elapsed < 10.0


# ===== v0.13.2：uv venv launcher re-exec 兼容 =====


def test_reexec_uv_grandchild_listens_is_owned(tmp_path, monkeypatch):
    """venv shim 退化为桩/退出，真正监听 8188 的是 uv 孙进程 → 仍 owned/RUNNING_MANAGED。"""
    svc = _make_service(tmp_path)
    monkeypatch.setattr(svc, "_spawn", lambda: 7777)  # spawn 返回的 shim pid
    # shim 已死（_pid_alive(7777)=False），但 uv 孙 8888 在监听且匹配 app
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(svc, "_matching_listener_pids", lambda: [8888])

    state = {"probed": 0}

    def probe():
        state["probed"] += 1
        # 前两次连接拒绝（冷启），第三次起健康（uv 孙就绪）
        return _Probe(online=state["probed"] >= 3, responded=state["probed"] >= 3, version="0.3.1")

    monkeypatch.setattr(svc, "_probe", probe)
    monkeypatch.setattr(svc, "_terminate_tree", lambda pid: None)

    snap = svc.start()
    assert snap.state == "RUNNING_MANAGED"
    assert snap.owned is True
    # 展示 pid 取真正监听的 uv 孙
    assert snap.pid == 8888

    # shim 已死：再次 status 仍判 RUNNING_MANAGED（不再误判 external）
    snap2 = svc.status()
    assert snap2.state == "RUNNING_MANAGED"
    assert snap2.owned is True


def test_starting_pid_change_refused_then_ready_no_error(tmp_path, monkeypatch):
    """启动期多次连接拒绝、监听 pid 变化，最终慢就绪：过程为 STARTING，不弹 ERROR。"""
    svc = _make_service(tmp_path, health_timeout_seconds=5.0)
    monkeypatch.setattr(svc, "_spawn", lambda: 7777)
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: True)  # 根树一直活
    # 监听 pid 从 8888 变 9999（re-exec），端口先拒绝后就绪
    listeners = {"seq": 0}
    monkeypatch.setattr(svc, "_matching_listener_pids", lambda: [8888 if listeners["seq"] < 2 else 9999])

    probe_calls = {"n": 0}

    def probe():
        probe_calls["n"] += 1
        if probe_calls["n"] < 3:
            return _Probe(online=False, responded=False)  # 连接拒绝
        return _Probe(online=True, responded=True, version="0.3.1")

    monkeypatch.setattr(svc, "_probe", probe)

    # 在 start() 阻塞窗口内并发 status()：必须返回 STARTING，不是 ERROR
    # （通过手工置位 _starting 模拟 start 轮询期）
    svc._starting = True
    svc._managed_active = True
    svc._state = "STARTING"
    concurrent = svc.status()
    assert concurrent.state == "STARTING"
    assert concurrent.owned is True
    svc._starting = False

    snap = svc.start()
    assert snap.state == "RUNNING_MANAGED"


def test_root_gone_and_no_listener_is_real_failure(tmp_path, monkeypatch):
    """根进程提前退出、无匹配监听 → 真失败 ERROR 并清理。"""
    svc = _make_service(tmp_path, health_timeout_seconds=5.0)
    monkeypatch.setattr(svc, "_spawn", lambda: 4242)
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: False)  # 根已死
    monkeypatch.setattr(svc, "_matching_listener_pids", lambda: [])  # 无监听孙
    monkeypatch.setattr(svc, "_probe", lambda: _Probe(online=False, responded=False))
    terminated: list[int] = []
    monkeypatch.setattr(svc, "_terminate_tree", lambda pid: terminated.append(pid))

    snap = svc.start()
    assert snap.state == "ERROR"
    # 即使根已死，也尝试清理（这里 _terminate_tree 被 mock，至少调用过根 pid 清理逻辑）
    assert svc._managed_active is False


def test_external_already_online_no_spawn_no_kill(tmp_path, monkeypatch):
    """启动前外部 carrier 已在线 → external，不 spawn、不杀。"""
    svc = _make_service(tmp_path)
    monkeypatch.setattr(svc, "_probe", lambda: _Probe(online=True, responded=True, version="0.3.0"))
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: False)
    spawned: list[int] = []
    monkeypatch.setattr(svc, "_spawn", lambda: spawned.append(1) or 1)
    terminated: list[int] = []
    monkeypatch.setattr(svc, "_terminate_tree", lambda pid: terminated.append(pid))

    snap = svc.start()
    assert snap.state == "RUNNING_EXTERNAL"
    assert snap.owned is False
    assert spawned == []          # 绝不拉第二个进程
    with pytest.raises(EngineNotOwned):
        svc.stop()
    assert terminated == []       # 绝不杀 external


def test_stop_terminates_uv_grandchild_tree_and_releases_port(tmp_path, monkeypatch):
    """managed stop 清理集合含 uv 监听孙整棵树，并复核端口释放。"""
    svc = _make_service(tmp_path)
    monkeypatch.setattr(svc, "_spawn", lambda: 7777)
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: True)
    uv_pid = {"v": 8888}
    monkeypatch.setattr(svc, "_matching_listener_pids", lambda: [uv_pid["v"]])

    online = {"value": True}

    def probe():
        if svc._pid is None:
            return _Probe(online=False, responded=False)  # spawn 前端口空闲
        return _Probe(online=online["value"], responded=online["value"], version="1.0")

    monkeypatch.setattr(svc, "_probe", probe)
    terminated: list[int] = []
    monkeypatch.setattr(svc, "_terminate_tree", lambda pid: terminated.append(pid))

    svc.start()
    terminated.clear()

    # stop 后端口释放（probe 翻离线）
    online["value"] = False
    snap = svc.stop()
    # 终止集合 = 根 7777 + uv 孙 8888
    assert 7777 in terminated
    assert 8888 in terminated
    assert snap.state == "STOPPED"
    assert svc._managed_active is False


def test_status_self_heals_from_stopped_to_managed(tmp_path, monkeypatch):
    """managed_active 下探活恢复：status 从 STOPPED 自动回 RUNNING_MANAGED。"""
    svc = _make_service(tmp_path)
    monkeypatch.setattr(svc, "_spawn", lambda: 7777)
    monkeypatch.setattr(svc, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(svc, "_matching_listener_pids", lambda: [8888])

    online = {"value": True}

    def probe():
        if svc._pid is None:
            return _Probe(online=False, responded=False)  # spawn 前端口空闲
        return _Probe(online=online["value"], responded=online["value"], version="1.0")

    monkeypatch.setattr(svc, "_probe", probe)
    monkeypatch.setattr(svc, "_terminate_tree", lambda pid: None)

    svc.start()
    # 模拟端口暂时掉线（崩溃/重启中）→ STOPPED 但保留 managed_active
    online["value"] = False
    s1 = svc.status()
    assert s1.state == "STOPPED"
    assert s1.owned is True  # 仍认为自己拥有

    # 探活恢复 → 自动回 RUNNING_MANAGED
    online["value"] = True
    s2 = svc.status()
    assert s2.state == "RUNNING_MANAGED"
    assert s2.owned is True
