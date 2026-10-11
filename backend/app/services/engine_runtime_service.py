"""受管 ComfyUI 运行时（Engine Runtime）——Studio 后端管理“自己的” ComfyUI 进程。

设计红线（务必遵守）：
- 固定端口 8188，**禁止自动换口**；
- Engine Runtime State 独立于 Job State，取值仅限：
  STOPPED / STARTING / RUNNING_MANAGED / RUNNING_EXTERNAL / STOPPING / PORT_CONFLICT / ERROR；
- **进程归属是硬安全**：只能停止 Studio 自己启动的 ComfyUI。

依赖 psutil 的理由：用于按 PID + 递归子进程树（``psutil.Process(pid).children(recursive=True)``）
精确归属与终止 Studio 自己启动的进程树，避免 ``taskkill /IM python.exe`` 误杀外部 ComfyUI
或其他 Python 进程。**严禁 taskkill /IM、严禁杀所有 Python、严禁杀 external。**

状态机::

    STOPPED ──start──▶ STARTING ──健康探测成功──▶ RUNNING_MANAGED
                          │
                          └──超时失败──▶ ERROR（并清理自己刚启动的进程树，不留孤儿）

    RUNNING_MANAGED ──stop/restart──▶ STOPPING ──▶ STOPPED
    外部 ComfyUI 占用 8188 ──▶ RUNNING_EXTERNAL（owned=false，不可杀）
    8188 被非 ComfyUI 占用 ──▶ PORT_CONFLICT

start/stop/restart 均为同步阻塞实现（subprocess/psutil/httpx），API 层用
``asyncio.to_thread`` 包装，避免阻塞事件循环。
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import psutil

from app.core.config import Settings
from app.core.errors import ConflictError

logger = logging.getLogger(__name__)

# ===== 固定常量（红线） =====
DEFAULT_HOST = "127.0.0.1"
FIXED_PORT = 8188  # 固定端口，禁止自动换口

# 运行时状态（独立于 Job State）
STATE_STOPPED = "STOPPED"
STATE_STARTING = "STARTING"
STATE_RUNNING_MANAGED = "RUNNING_MANAGED"
STATE_RUNNING_EXTERNAL = "RUNNING_EXTERNAL"
STATE_STOPPING = "STOPPING"
STATE_PORT_CONFLICT = "PORT_CONFLICT"
STATE_ERROR = "ERROR"

# 启动后轮询健康的节奏
START_HEALTH_TIMEOUT_S = 60.0
START_HEALTH_INTERVAL_S = 1.0
# stop 时 terminate 的宽限期，超时再 kill
TERMINATE_GRACE_S = 10.0
# 健康探测超时
PROBE_TIMEOUT_S = 3.0

CREATE_NO_WINDOW = 0x08000000  # Windows：避免弹控制台


class EngineNotOwned(ConflictError):
    """对 external（非 Studio 启动）引擎调用 stop/restart。"""

    status_code = 409
    code = "ENGINE_NOT_OWNED"
    message = "引擎非 Studio 托管，拒绝停止"


class EnginePortConflict(ConflictError):
    """8188 被非 ComfyUI 占用，start 拒绝。"""

    status_code = 409
    code = "ENGINE_PORT_CONFLICT"
    message = "端口已被非 ComfyUI 进程占用"


@dataclass
class _Probe:
    """一次端口探测结果。"""

    online: bool = False          # 是否为健康的 ComfyUI（/system_stats 命中）
    responded: bool = False       # 端口是否有任何 HTTP 响应（即有人监听）
    version: str = ""


@dataclass
class RuntimeSnapshot:
    """冻结的 API 契约返回体（见任务约定）。"""

    state: str
    host: str
    port: int
    owned: bool
    pid: int | None
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
            "started_at": self.started_at,
            "detail": self.detail,
            "log_location": self.log_location,
            "health": self.health,
        }


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EngineRuntimeService:
    """单例服务：管理 Studio 自己的 ComfyUI 进程。

    所有阻塞方法（spawn/probe/terminate）均为同步，便于测试用 monkeypatch 替换；
    API 层负责 ``asyncio.to_thread`` 包装。
    """

    def __init__(self, settings: Settings) -> None:
        cfg = settings.engine_runtime or {}
        self.host = str(cfg.get("host", DEFAULT_HOST))
        # 端口红线：默认固定 8188；配置仅用于显式覆盖，绝不自动 +1
        self.port = int(cfg.get("port", FIXED_PORT))
        self.managed = bool(cfg.get("managed", True))
        self.python_exe = str(cfg.get("python_exe", ""))
        self.working_dir = str(cfg.get("working_dir", ""))
        self.entrypoint = str(cfg.get("entrypoint", "main.py"))
        self.extra_args = [str(a) for a in (cfg.get("extra_args") or [])]
        self.launch_command = cfg.get("launch_command") or None

        logs_dir = settings.storage.data_root / "logs" / "engine"
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.log_location = str(logs_dir / "comfyui-managed.log")

        # 受管进程记录
        self._pid: int | None = None
        self._cmd: list[str] = []
        self._cwd: str | None = None
        self._started_at: str | None = None
        self._state: str = STATE_STOPPED

    # ===== 探测 / 进程树：以下为可替换 seam（测试 monkeypatch） =====

    def _probe(self) -> _Probe:
        """探测 host:port 是否为健康 ComfyUI。"""
        url = f"http://{self.host}:{self.port}/system_stats"
        try:
            resp = httpx.get(url, timeout=PROBE_TIMEOUT_S, trust_env=False)
        except httpx.HTTPError:
            # 连接拒绝 / 超时 / 网络错误：端口无人监听
            return _Probe(online=False, responded=False)
        # 有 HTTP 响应 → 端口被占用
        try:
            data = resp.json()
        except Exception:
            return _Probe(online=False, responded=True)
        if isinstance(data, dict) and "system" in data:
            version = str(data.get("system", {}).get("comfyui_version", ""))
            return _Probe(online=True, responded=True, version=version)
        return _Probe(online=False, responded=True)

    def _pid_alive(self, pid: int) -> bool:
        try:
            p = psutil.Process(pid)
            return p.is_running()
        except psutil.Error:
            return False

    def _spawn(self) -> int:
        """以受管方式启动 ComfyUI 子进程，返回其 PID。"""
        if self.launch_command:
            argv = [str(a) for a in self.launch_command]
        else:
            if not self.python_exe or not self.working_dir:
                raise RuntimeError("engine_runtime 缺少 python_exe / working_dir，无法启动受管 ComfyUI")
            argv = [self.python_exe, self.entrypoint, *self.extra_args]

        log_fh = open(self.log_location, "ab")
        kwargs: dict[str, Any] = {
            "cwd": self.working_dir or None,
            "stdout": log_fh,
            "stderr": subprocess.STDOUT,
        }
        if os.name == "nt":
            kwargs["creationflags"] = CREATE_NO_WINDOW
        proc = subprocess.Popen(argv, **kwargs)
        self._cmd = argv
        self._cwd = self.working_dir or None
        return proc.pid

    def _terminate_tree(self, pid: int) -> None:
        """只终止指定 PID 及其递归子进程树（绝不 taskkill /IM、绝不杀外部）。"""
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

    def _snapshot(self, probe: _Probe | None = None) -> RuntimeSnapshot:
        probe = probe or self._probe()
        health = {
            "online": probe.online,
            "engine_name": "comfyui",
            "engine_version": probe.version,
        }
        return RuntimeSnapshot(
            state=self._state,
            host=self.host,
            port=self.port,
            owned=self._pid is not None,
            pid=self._pid,
            started_at=self._started_at,
            detail=self._detail_for(probe),
            log_location=self.log_location,
            health=health,
        )

    def _detail_for(self, probe: _Probe) -> str:
        if self._state == STATE_RUNNING_MANAGED:
            return f"受管 ComfyUI 运行中 (pid={self._pid})"
        if self._state == STATE_RUNNING_EXTERNAL:
            return f"检测到外部 ComfyUI @ {self.host}:{self.port}"
        if self._state == STATE_PORT_CONFLICT:
            return f"{self.host}:{self.port} 被非 ComfyUI 进程占用"
        if self._state == STATE_ERROR:
            return "受管 ComfyUI 启动失败"
        if probe.responded:
            return f"{self.host}:{self.port} 有响应"
        return f"{self.host}:{self.port} 无响应"

    def _recompute_state(self) -> _Probe:
        """根据受管进程存活 + 端口探测推导当前状态。"""
        probe = self._probe()
        managed_alive = self._pid is not None and self._pid_alive(self._pid)
        if managed_alive and probe.online:
            self._state = STATE_RUNNING_MANAGED
        elif probe.online:
            # 端口健康，但不是我们启动的（或受管进程已消失）
            self._state = STATE_RUNNING_EXTERNAL
            self._clear_record()
        elif probe.responded:
            self._state = STATE_PORT_CONFLICT
        else:
            # 端口关闭
            if managed_alive:
                # 受管进程还活着但端口没起来：视为异常（启动未完成 / 已僵死）
                self._state = STATE_ERROR
            else:
                self._state = STATE_STOPPED
                self._clear_record()
        return probe

    def _clear_record(self) -> None:
        self._pid = None
        self._cmd = []
        self._cwd = None
        self._started_at = None

    # ===== 公共操作 =====

    def status(self) -> RuntimeSnapshot:
        probe = self._recompute_state()
        return self._snapshot(probe)

    def start(self) -> RuntimeSnapshot:
        current = self._recompute_state()
        # 幂等：已在跑（含 STARTING）或外部已占用，不得再起第二个进程
        if self._state in (STATE_RUNNING_MANAGED, STATE_STARTING, STATE_RUNNING_EXTERNAL):
            return self._snapshot(current)
        if self._state == STATE_PORT_CONFLICT:
            raise EnginePortConflict()

        self._state = STATE_STARTING
        try:
            self._pid = self._spawn()
            self._started_at = _utc_iso()
        except Exception as error:  # noqa: BLE001
            logger.warning("受管 ComfyUI 启动失败: %s", error)
            self._state = STATE_ERROR
            return self._snapshot(_Probe())

        # 轮询健康
        deadline = time.monotonic() + START_HEALTH_TIMEOUT_S
        healthy = False
        while time.monotonic() < deadline:
            probe = self._probe()
            if probe.online:
                healthy = True
                break
            time.sleep(START_HEALTH_INTERVAL_S)

        if healthy:
            self._state = STATE_RUNNING_MANAGED
            return self._snapshot(self._probe())

        # 失败：清理自己刚启动的进程树，不留孤儿
        logger.warning("受管 ComfyUI 健康探测超时，清理 pid=%s", self._pid)
        try:
            self._terminate_tree(self._pid)
        except Exception:  # noqa: BLE001
            logger.warning("清理受管 ComfyUI 进程树失败", exc_info=True)
        self._clear_record()
        self._state = STATE_ERROR
        return self._snapshot(_Probe())

    def stop(self) -> RuntimeSnapshot:
        current = self._recompute_state()
        if self._state == STATE_RUNNING_EXTERNAL:
            raise EngineNotOwned()
        if self._state in (STATE_STOPPED, STATE_PORT_CONFLICT, STATE_ERROR) and self._pid is None:
            return self._snapshot(current)

        self._state = STATE_STOPPING
        if self._pid is not None:
            try:
                self._terminate_tree(self._pid)
            finally:
                self._clear_record()
        self._state = STATE_STOPPED
        return self._snapshot(_Probe(responded=False))

    def restart(self) -> RuntimeSnapshot:
        current = self._recompute_state()
        if self._state == STATE_RUNNING_EXTERNAL:
            raise EngineNotOwned()
        # 先停掉 owned 的受管进程
        if self._pid is not None:
            self._state = STATE_STOPPING
            try:
                self._terminate_tree(self._pid)
            finally:
                self._clear_record()
            self._state = STATE_STOPPED
        return self.start()
