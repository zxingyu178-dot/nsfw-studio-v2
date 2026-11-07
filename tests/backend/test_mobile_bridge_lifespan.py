"""Studio lifespan 对 Mobile Review Bridge 的回归测试。

所有进程、端口与健康探测都通过 ``MobileReviewRuntimeService`` seam 替换；
本文件不会连接 8877，也不会创建真实子进程。
"""
from __future__ import annotations

import dataclasses
import concurrent.futures
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.mobile_review_runtime_service import MobileReviewRuntimeService


_HEALTHY = {"product": "nsfw-studio", "status": "ok", "version": "test"}


class _BridgeHarness:
    def __init__(self, *, external_healthy: bool = False, fail_spawn: bool = False) -> None:
        self.external_healthy = external_healthy
        self.fail_spawn = fail_spawn
        self.allow_owned_health = threading.Event()
        self.spawn_attempted = threading.Event()
        self.spawned = threading.Event()
        self._lock = threading.Lock()
        self._alive: set[int] = set()
        self.spawned_pids: list[int] = []
        self.terminated_pids: list[int] = []
        self.probe_thread_ids: set[int] = set()

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            MobileReviewRuntimeService, "_probe", lambda service: self.probe(service)
        )
        monkeypatch.setattr(
            MobileReviewRuntimeService, "_spawn", lambda service: self.spawn(service)
        )
        monkeypatch.setattr(
            MobileReviewRuntimeService, "_pid_alive", lambda _service, pid: self.pid_alive(pid)
        )
        monkeypatch.setattr(
            MobileReviewRuntimeService,
            "_terminate_tree",
            lambda _service, pid: self.terminate_tree(pid),
        )

    def probe(self, service: MobileReviewRuntimeService) -> dict | None:
        with self._lock:
            self.probe_thread_ids.add(threading.get_ident())
            owned_alive = service._pid is not None and service._pid in self._alive
        if self.external_healthy and service._pid is None:
            return dict(_HEALTHY)
        if owned_alive and self.allow_owned_health.is_set():
            return dict(_HEALTHY)
        return None

    def spawn(self, service: MobileReviewRuntimeService) -> int:
        self.spawn_attempted.set()
        if self.fail_spawn:
            raise OSError("fake bridge spawn failure")
        pid = 48771
        service._parent_pid = 42
        with self._lock:
            self._alive.add(pid)
            self.spawned_pids.append(pid)
        self.spawned.set()
        return pid

    def pid_alive(self, pid: int) -> bool:
        with self._lock:
            return pid in self._alive

    def terminate_tree(self, pid: int) -> None:
        with self._lock:
            self.terminated_pids.append(pid)
            self._alive.discard(pid)
        # 无论实现在哪条清理路径调用 terminate，都保证慢启动探测可退出。
        self.allow_owned_health.set()


def _settings_with_mobile_review(settings, *, enabled: bool):
    mobile_review = dict(settings.mobile_review or {})
    mobile_review.update(
        enabled=enabled,
        host="127.0.0.1",
        port=8877,
        health_timeout_seconds=30.0,
    )
    return dataclasses.replace(settings, mobile_review=mobile_review)


def _safety_release(event: threading.Event) -> threading.Timer:
    """错误实现若阻塞 TestClient.__enter__，也有有限等待兜底。

    留出临时数据库 bootstrap 预算；是否阻塞由尚未释放的健康事件判断。
    """
    timer = threading.Timer(10.0, event.set)
    timer.daemon = True
    timer.start()
    return timer


def test_enabled_bridge_starts_in_background_without_blocking_studio_health(
    settings, monkeypatch,
):
    harness = _BridgeHarness()
    harness.install(monkeypatch)
    app = create_app(_settings_with_mobile_review(settings, enabled=True))
    watchdog = _safety_release(harness.allow_owned_health)

    try:
        with TestClient(app) as client:
            assert harness.spawned.wait(timeout=1.0), "enabled Bridge 应自动请求启动"
            assert not harness.allow_owned_health.is_set(), "Bridge 仍应处于慢健康等待"
            assert client.get("/api/v1/health").status_code == 200
    finally:
        harness.allow_owned_health.set()
        watchdog.cancel()


def test_disabled_bridge_does_not_autostart(settings, monkeypatch):
    harness = _BridgeHarness()
    harness.install(monkeypatch)
    app = create_app(_settings_with_mobile_review(settings, enabled=False))

    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert not harness.spawn_attempted.wait(timeout=0.1)

    assert harness.terminated_pids == []


@pytest.mark.parametrize("autostart", [True, False], ids=["automatic", "manual"])
def test_owned_bridge_is_reclaimed_when_studio_exits(
    settings, monkeypatch, autostart,
):
    harness = _BridgeHarness()
    harness.allow_owned_health.set()
    harness.install(monkeypatch)
    app = create_app(_settings_with_mobile_review(settings, enabled=autostart))

    with TestClient(app) as client:
        if autostart:
            assert harness.spawned.wait(timeout=1.0)
        else:
            response = client.post("/api/v1/mobile-review/runtime/start")
            assert response.status_code == 200
            assert harness.spawned.is_set()

    assert harness.spawned_pids == [48771]
    assert harness.terminated_pids == [48771]


def test_bridge_autostart_failure_does_not_fail_studio_startup(settings, monkeypatch):
    harness = _BridgeHarness(fail_spawn=True)
    harness.install(monkeypatch)
    app = create_app(_settings_with_mobile_review(settings, enabled=True))

    with TestClient(app) as client:
        assert harness.spawn_attempted.wait(timeout=1.0)
        assert client.get("/api/v1/health").status_code == 200

    assert harness.terminated_pids == []


def test_cold_bridge_start_is_joined_and_owned_pid_reclaimed_on_early_exit(
    settings, monkeypatch,
):
    harness = _BridgeHarness()
    harness.install(monkeypatch)
    app = create_app(_settings_with_mobile_review(settings, enabled=True))
    watchdog = _safety_release(harness.allow_owned_health)

    try:
        with TestClient(app):
            assert harness.spawned.wait(timeout=1.0)
            assert not harness.allow_owned_health.is_set()
    finally:
        harness.allow_owned_health.set()
        watchdog.cancel()

    assert harness.terminated_pids == [48771]
    alive_thread_ids = {thread.ident for thread in threading.enumerate() if thread.is_alive()}
    assert harness.probe_thread_ids.isdisjoint(alive_thread_ids)


def test_external_healthy_bridge_is_never_terminated(settings, monkeypatch):
    harness = _BridgeHarness(external_healthy=True)
    harness.install(monkeypatch)
    app = create_app(_settings_with_mobile_review(settings, enabled=True))

    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert not harness.spawn_attempted.wait(timeout=0.1)

    assert harness.spawned_pids == []
    assert harness.terminated_pids == []


def test_manual_start_during_autostart_reuses_child_and_status_stays_starting(
    settings, monkeypatch,
):
    harness = _BridgeHarness()
    harness.install(monkeypatch)
    app = create_app(_settings_with_mobile_review(settings, enabled=True))
    watchdog = _safety_release(harness.allow_owned_health)
    try:
        with TestClient(app):
            assert harness.spawned.wait(timeout=1.0)
            runtime = app.state.mobile_review_runtime
            status = runtime.status()
            assert status.state == "STARTING"
            assert status.owned
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                second_start = executor.submit(runtime.start)
                harness.allow_owned_health.set()
                assert second_start.result(timeout=2.0).state == "RUNNING"
            assert harness.spawned_pids == [48771]
    finally:
        harness.allow_owned_health.set()
        watchdog.cancel()
    assert harness.terminated_pids == [48771]


@pytest.mark.parametrize("action", ["stop", "restart"])
def test_manual_action_interrupts_bridge_cold_start(settings, monkeypatch, action):
    harness = _BridgeHarness()
    harness.install(monkeypatch)
    app = create_app(_settings_with_mobile_review(settings, enabled=True))
    watchdog = _safety_release(harness.allow_owned_health)
    try:
        with TestClient(app) as client:
            assert harness.spawned.wait(timeout=1.0)
            began = time.monotonic()
            response = client.post(f"/api/v1/mobile-review/runtime/{action}")
            assert response.status_code == 200
            assert time.monotonic() - began < 2.0
            assert response.json()["state"] == ("STOPPED" if action == "stop" else "RUNNING")
            assert len(harness.spawned_pids) == (1 if action == "stop" else 2)
    finally:
        harness.allow_owned_health.set()
        watchdog.cancel()
