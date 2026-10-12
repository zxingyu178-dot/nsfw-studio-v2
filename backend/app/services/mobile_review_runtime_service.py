"""Mobile Review Bridge 受管运行时（Phase 0.13）。

复用 EngineRuntimeService 的成熟思路，但只管**自己启动的** Bridge 进程：

- 状态机：STOPPED / STARTING / RUNNING / STOPPING / PORT_CONFLICT / ERROR；
- 固定端口 8767，**禁止自动换口**；8000 始终 loopback，本服务绝不触碰；
- **进程归属是硬安全**：只停止 Studio 自己启动的 PID，严禁 ``taskkill /IM python.exe``；
- **Orphan 防护**：启动时记录父 PID（主 Studio）并经环境变量传给 Bridge，
  主 Studio 退出后 Bridge 自行退出（见 mobile_main 的 parent-watch）；
- 启动命令固定：``uvicorn app.mobile_main:app --host 0.0.0.0 --port 8767``。
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
import psutil

from app.core.config import Settings
from app.core.errors import ConflictError

logger = logging.getLogger(__name__)

DEFAULT_HOST = "0.0.0.0"
FIXED_PORT = 8767

STATE_STOPPED = "STOPPED"
STATE_STARTING = "STARTING"
STATE_RUNNING = "RUNNING"
STATE_STOPPING = "STOPPING"
STATE_PORT_CONFLICT = "PORT_CONFLICT"
STATE_ERROR = "ERROR"

START_HEALTH_INTERVAL_S = 0.5
DEFAULT_HEALTH_TIMEOUT_S = 30.0
TERMINATE_GRACE_S = 10.0
PROBE_TIMEOUT_S = 3.0
CREATE_NO_WINDOW = 0x08000000

ENV_PARENT_PID = "NSFW_STUDIO_MOBILE_BRIDGE_PARENT_PID"


class BridgeNotOwned(ConflictError):
    status_code = 409
    code = "BRIDGE_NOT_OWNED"
    message = "Bridge 非 Studio 托管，拒绝停止"


class BridgePortConflict(ConflictError):
    status_code = 409
    code = "BRIDGE_PORT_CONFLICT"
    message = "8767 已被非 Bridge 进程占用"


@dataclass
class BridgeSnapshot:
    state: str
    host: str
    port: int
    owned: bool
    pid: int | None
    parent_pid: int | None
    started_at: str | None
    detail: str
    log_location: str | None
    health: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "host": self.host,
            "port": self.port,
            "owned": self.owned,
            "pid": self.pid,
            "parent_pid": self.parent_pid,
            "started_at": self.started_at,
            "detail": self.detail,
            "log_location": self.log_location,
            "health": self.health,
        }


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class MobileReviewRuntimeService:
    """单例服务：管理 Studio 自己的 Mobile Review Bridge (uvicorn) 子进程。"""

    def __init__(self, settings: Settings) -> None:
        cfg = settings.mobile_review or {}
        self.enabled = bool(cfg.get("enabled", False))
        self.host = str(cfg.get("host", DEFAULT_HOST))
        self.port = int(cfg.get("port", FIXED_PORT))
        self.python_exe = str(cfg.get("python_exe", ""))
        self.working_dir = str(cfg.get("working_dir", ""))
        self.health_timeout = float(cfg.get("health_timeout_seconds", DEFAULT_HEALTH_TIMEOUT_S))

        logs_dir = settings.storage.data_root / "logs" / "mobile"
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.log_location = str(logs_dir / "mobile-review-bridge.log")

        self._pid: int | None = None
        self._parent_pid: int | None = None
        self._started_at: str | None = None
        self._state: str = STATE_STOPPED

    # ===== 可替换 seam（测试 monkeypatch） =====

    def _probe(self) -> dict[str, Any] | None:
        """探测 host:port 是否为健康的 Bridge；返回 health dict 或 None。"""
        url = f"http://{self.host}:{self.port}/mobile/system/health"
        try:
            resp = httpx.get(url, timeout=PROBE_TIMEOUT_S, trust_env=False)
        except httpx.HTTPError:
            return None
        try:
            data = resp.json()
        except Exception:
            return {"responded": True}
        # envelope 包一层 {success,data}；health 本体在 data 里
        payload = data.get("data", data) if isinstance(data, dict) else {}
        if isinstance(payload, dict) and payload.get("product") == "nsfw-studio":
            return payload
        return {"responded": True}

    def _pid_alive(self, pid: int) -> bool:
        try:
            return psutil.Process(pid).is_running()
        except psutil.Error:
            return False

    def _spawn(self) -> int:
        """以受管方式启动 Bridge uvicorn 子进程，返回其 PID。"""
        python = self.python_exe or "python"
        argv = [
            python, "-m", "uvicorn", "app.mobile_main:app",
            "--host", self.host, "--port", str(self.port),
        ]
        env = dict(os.environ)
        # Orphan 防护：把主 Studio PID 告诉 Bridge，主 Studio 退出后 Bridge 自行退出
        self._parent_pid = os.getpid()
        env[ENV_PARENT_PID] = str(self._parent_pid)

        log_fh = open(self.log_location, "ab")
        kwargs: dict[str, Any] = {
            "cwd": self.working_dir or None,
            "stdout": log_fh,
            "stderr": subprocess.STDOUT,
            "env": env,
        }
        if os.name == "nt":
            kwargs["creationflags"] = CREATE_NO_WINDOW
        proc = subprocess.Popen(argv, **kwargs)
        log_fh.close()
        return proc.pid

    def _terminate_tree(self, pid: int) -> None:
        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return
        children = parent.children(recursive=True)
        procs = [parent, *children]
        for p in procs:
            try:
                p.terminate()
            except psutil.Error:
                pass
        _gone, alive = psutil.wait_procs(procs, timeout=TERMINATE_GRACE_S)
        for p in alive:
            try:
                p.kill()
            except psutil.Error:
                pass

    # ===== 状态推导 =====

    def _clear_record(self) -> None:
        self._pid = None
        self._parent_pid = None
        self._started_at = None

    def _snapshot(self, probe: dict | None = None) -> BridgeSnapshot:
        return BridgeSnapshot(
            state=self._state,
            host=self.host,
            port=self.port,
            owned=self._pid is not None,
            pid=self._pid,
            parent_pid=self._parent_pid,
            started_at=self._started_at,
            detail=f"{self.host}:{self.port} " + ("健康" if probe else "无响应"),
            log_location=self.log_location,
            health=probe or {},
        )

    def _recompute(self) -> dict | None:
        probe = self._probe()
        managed_alive = self._pid is not None and self._pid_alive(self._pid)
        if managed_alive and probe is not None and probe.get("product") == "nsfw-studio":
            self._state = STATE_RUNNING
        elif probe is not None:
            # 端口是 Bridge 但不是我们启动的（或受管进程已消失）
            if probe.get("product") == "nsfw-studio":
                self._state = STATE_RUNNING
                self._clear_record()
            else:
                self._state = STATE_PORT_CONFLICT
        elif managed_alive:
            self._state = STATE_ERROR
        else:
            self._state = STATE_STOPPED
            self._clear_record()
        return probe

    def status(self) -> BridgeSnapshot:
        probe = self._recompute()
        return self._snapshot(probe)

    def start(self) -> BridgeSnapshot:
        probe = self._recompute()
        if self._state in (STATE_RUNNING, STATE_STARTING):
            return self._snapshot(probe)
        if self._state == STATE_PORT_CONFLICT:
            raise BridgePortConflict()

        self._state = STATE_STARTING
        try:
            self._pid = self._spawn()
            self._started_at = _utc_iso()
        except Exception as error:  # noqa: BLE001
            logger.warning("Mobile Bridge 启动失败: %s", error)
            self._state = STATE_ERROR
            self._clear_record()
            return self._snapshot(None)

        deadline = time.monotonic() + self.health_timeout
        healthy = False
        while time.monotonic() < deadline:
            probe = self._probe()
            if probe is not None and probe.get("product") == "nsfw-studio":
                healthy = True
                break
            time.sleep(START_HEALTH_INTERVAL_S)

        if healthy:
            self._state = STATE_RUNNING
            return self._snapshot(self._probe())

        logger.warning("Mobile Bridge 健康探测超时，清理 pid=%s", self._pid)
        try:
            self._terminate_tree(self._pid)
        except Exception:  # noqa: BLE001
            logger.warning("清理 Mobile Bridge 进程树失败", exc_info=True)
        self._clear_record()
        self._state = STATE_ERROR
        return self._snapshot(None)

    def stop(self) -> BridgeSnapshot:
        self._recompute()
        if self._state == STATE_PORT_CONFLICT:
            raise BridgeNotOwned()
        if self._state == STATE_STOPPED and self._pid is None:
            return self._snapshot(None)

        self._state = STATE_STOPPING
        if self._pid is not None:
            try:
                self._terminate_tree(self._pid)
            finally:
                self._clear_record()
        self._state = STATE_STOPPED
        return self._snapshot(None)

    def restart(self) -> BridgeSnapshot:
        self._recompute()
        if self._state == STATE_PORT_CONFLICT:
            raise BridgeNotOwned()
        if self._pid is not None:
            self._state = STATE_STOPPING
            try:
                self._terminate_tree(self._pid)
            finally:
                self._clear_record()
            self._state = STATE_STOPPED
        return self.start()
