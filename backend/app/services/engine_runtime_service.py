"""受管 ComfyUI 运行时（Engine Runtime）——Studio 后端管理“自己的” ComfyUI 进程。

设计红线（务必遵守）：
- 固定端口 8188，**禁止自动换口**；
- Engine Runtime State 独立于 Job State，取值仅限：
  STOPPED / STARTING / RUNNING_MANAGED / RUNNING_EXTERNAL / STOPPING / PORT_CONFLICT / ERROR；
- **进程归属是硬安全**：只能停止 Studio 自己启动的 ComfyUI。

依赖 psutil 的理由：用于按 PID + 递归子进程树（``psutil.Process(pid).children(recursive=True)``）
精确归属与终止 Studio 自己启动的进程树，避免 ``taskkill /IM python.exe`` 误杀外部 ComfyUI
或其他 Python 进程。**严禁 taskkill /IM、严禁杀所有 Python、严禁杀 external。**

v0.13.2 健壮化（兼容 uv venv launcher re-exec）：
- uv 0.12 的 ``venv/Scripts/python.exe`` 是 ~45KB 的 launcher 桩，启动时 re-exec 到 uv 自管理
  cpython（``%APPDATA%\\uv\\python\\cpython-3.12-...\\python.exe main.py``），**实际 LISTEN 8188 的
  是这个 uv base 孙进程**，而不是我们 spawn 返回的直接子 pid。因此：
  - 归属不再以"直接子 pid 是否存活/是否监听"为唯一判据，而以"**本会话是否在端口空闲时发起过启动**
    （``_managed_active``）+ 端口 HTTP 健康"为准；
  - 启动期（冷启约 3 分钟）即使受管 pid 还在、端口没起，也只报 **STARTING**，不再误判 ERROR；
  - ``status()`` 以实际探活为准，``_managed_active`` 下探活恢复可从 STOPPED/ERROR/STARTING 自动回
    RUNNING_MANAGED（顶栏引擎灯与真实一致）；
  - stop 清理集合 = 原始 spawn 根进程树 + 当前 LISTEN 8188 且匹配 app 的进程递归子树（含 uv 孙）。

状态机::

    STOPPED ──start(端口空闲)──▶ STARTING ──HTTP /system_stats 200──▶ RUNNING_MANAGED
                                    │
                                    └──根与匹配监听都消失/超时──▶ ERROR（清理自己的树）

    RUNNING_MANAGED ──stop/restart──▶ STOPPING ──▶ STOPPED
    外部 ComfyUI 已占用 8188 ──▶ RUNNING_EXTERNAL（owned=false，不 spawn、不杀）
    8188 被非 ComfyUI 占用 ──▶ PORT_CONFLICT

start/stop/restart 均为同步阻塞实现（subprocess/psutil/httpx），API 层用
``asyncio.to_thread`` 包装，避免阻塞事件循环。
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
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
# 默认健康等待上限：需覆盖 ComfyUI 冷启动（含 ComfyUI-Manager prestartup/网络重试 + uv re-exec）
# 的真实耗时（真机约 3 分钟）。v0.13.2 由 240 提到 300，可被 engine_runtime.health_timeout_seconds 覆盖。
DEFAULT_HEALTH_TIMEOUT_S = 300.0
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
        # 受管启动健康等待上限（秒）：可配置，默认覆盖慢冷启动（含 uv re-exec）；其余状态/幂等/进程树逻辑不变
        self.health_timeout = float(cfg.get("health_timeout_seconds", DEFAULT_HEALTH_TIMEOUT_S))

        logs_dir = settings.storage.data_root / "logs" / "engine"
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.log_location = str(logs_dir / "comfyui-managed.log")

        # 受管进程记录
        self._pid: int | None = None       # 原始 spawn 根（venv shim），仅用于清理根树
        self._cmd: list[str] = []
        self._cwd: str | None = None
        self._started_at: str | None = None
        self._state: str = STATE_STOPPED
        # v0.13.2：归属以"本会话是否在端口空闲时发起过启动"为准（兼容 re-exec 孙进程监听）
        self._managed_active: bool = False
        # v0.13.2：start() 阻塞健康轮询窗口内，并发 status()/_recompute_state 一律报 STARTING
        self._starting: bool = False

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

    def _listening_pids(self) -> list[int]:
        """当前 LISTEN 本服务端口的进程 pid 列表（psutil seam，测试可 monkeypatch）。"""
        pids: list[int] = []
        try:
            for conn in psutil.net_connections(kind="tcp"):
                if conn.status != psutil.CONN_LISTEN:
                    continue
                if conn.laddr and conn.laddr.port == self.port:
                    if conn.pid:
                        pids.append(conn.pid)
        except psutil.Error:
            pass
        return pids

    def _pid_matches_app(self, pid: int) -> bool:
        """判断某 pid 是否为 ComfyUI app（cmdline 含 main.py 且 cwd 指向配置 working_dir）。

        用于"定位与清理"，而非唯一归属判据（cmdline/cwd 匹配无法区分我们拉的 vs 用户手动起的）。
        """
        try:
            p = psutil.Process(pid)
            cmd = " ".join(p.cmdline() or [])
            cwd = ""
            try:
                cwd = p.cwd() or ""
            except psutil.Error:
                cwd = ""
        except psutil.Error:
            return False
        if self.entrypoint not in cmd:
            return False
        if self.working_dir:
            norm_cwd = os.path.normcase(os.path.abspath(cwd))
            norm_wd = os.path.normcase(os.path.abspath(self.working_dir))
            if norm_cwd != norm_wd:
                return False
        return True

    def _matching_listener_pids(self) -> list[int]:
        """LISTEN 本端口且匹配 app 的 pid（含 uv re-exec 孙进程）。"""
        return [pid for pid in self._listening_pids() if self._pid_matches_app(pid)]

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
        # Popen 已把该句柄继承给子进程（作为其 stdout）；立即关闭父进程(Studio)持有的副本，
        # 避免每次受管 start 在父进程泄漏一个 OS 文件句柄。子进程保留自己的副本，可继续写日志。
        log_fh.close()
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
        # 展示用 pid：优先取当前匹配监听进程（re-exec 后真正绑定端口的那个），否则回退到 spawn 根
        show_pid = self._pid
        if self._state == STATE_RUNNING_MANAGED:
            matches = self._matching_listener_pids()
            if matches:
                show_pid = matches[0]
        health = {
            "online": probe.online,
            "engine_name": "comfyui",
            "engine_version": probe.version,
        }
        owned = self._state in (STATE_RUNNING_MANAGED,) or (
            self._state in (STATE_STARTING, STATE_STOPPED) and self._managed_active
        )
        return RuntimeSnapshot(
            state=self._state,
            host=self.host,
            port=self.port,
            owned=owned,
            pid=show_pid,
            started_at=self._started_at,
            detail=self._detail_for(probe),
            log_location=self.log_location,
            health=health,
        )

    def _detail_for(self, probe: _Probe) -> str:
        if self._state == STATE_STARTING:
            return "受管 ComfyUI 启动中（冷启约数分钟，可后台等待）"
        if self._state == STATE_RUNNING_MANAGED:
            return f"受管 ComfyUI 运行中 @ {self.host}:{self.port}"
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
        """根据"本会话是否发起过启动"+ 端口探活推导当前状态（兼容 re-exec 孙进程监听）。"""
        # start() 阻塞健康轮询窗口内：并发 status() 一律报 STARTING，不翻 ERROR（修复冷启误报）
        if self._starting:
            probe = self._probe()
            if probe.online:
                self._state = STATE_RUNNING_MANAGED
            else:
                self._state = STATE_STARTING
            return probe

        probe = self._probe()
        if probe.online:
            if self._managed_active:
                # 本会话拉起的（无论监听 pid 是 shim 还是 uv 孙）一律 owned
                self._state = STATE_RUNNING_MANAGED
            else:
                # 端口健康但不是本会话拉的（Studio 刚重启 / 用户手动起的 carrier）→ external，不杀
                self._state = STATE_RUNNING_EXTERNAL
                self._clear_record(keep_active=False)
        elif probe.responded:
            self._state = STATE_PORT_CONFLICT
        else:
            # 端口关闭
            if self._managed_active:
                # 我们曾发起启动但端口暂未/不再监听：不主动翻 STOPPED 清记录，
                # 保持 managed_active，使下次探活恢复可自动回 RUNNING_MANAGED（自恢复）。
                self._state = STATE_STOPPED
            else:
                self._state = STATE_STOPPED
                self._clear_record(keep_active=False)
        return probe

    def _clear_record(self, *, keep_active: bool = True) -> None:
        self._pid = None
        self._cmd = []
        self._cwd = None
        self._started_at = None
        if not keep_active:
            self._managed_active = False
        self._starting = False

    def _root_or_listener_alive(self) -> bool:
        """启动轮询期：受管根树或匹配监听是否还活着（用于尽早判真失败）。"""
        if self._pid is not None and self._pid_alive(self._pid):
            return True
        return bool(self._matching_listener_pids())

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
        self._starting = True
        self._managed_active = True
        try:
            self._pid = self._spawn()
            self._started_at = _utc_iso()
        except Exception as error:  # noqa: BLE001
            logger.warning("受管 ComfyUI 启动失败: %s", error)
            self._starting = False
            self._managed_active = False
            self._state = STATE_ERROR
            return self._snapshot(_Probe())

        # 轮询健康（截止由可配置的 self.health_timeout 决定，默认 300s 覆盖慢冷启 + re-exec）
        deadline = time.monotonic() + self.health_timeout
        healthy = False
        while time.monotonic() < deadline:
            probe = self._probe()
            if probe.online:
                healthy = True
                break
            # 真失败：根与匹配监听都消失 → 不必等满超时
            if not self._root_or_listener_alive():
                logger.warning("受管 ComfyUI 根进程与匹配监听均消失，提前判失败 pid=%s", self._pid)
                break
            time.sleep(START_HEALTH_INTERVAL_S)

        if healthy:
            self._starting = False
            self._state = STATE_RUNNING_MANAGED
            return self._snapshot(self._probe())

        # 失败：清理自己刚启动的进程树（含 uv 孙），不留孤儿
        logger.warning("受管 ComfyUI 健康探测超时/失败，清理 pid=%s", self._pid)
        self._cleanup_managed_tree()
        self._starting = False
        self._managed_active = False
        self._clear_record(keep_active=False)
        self._state = STATE_ERROR
        return self._snapshot(_Probe())

    def _cleanup_managed_tree(self) -> None:
        """终止集合 = 原始 spawn 根树 + 当前 LISTEN 8188 且匹配 app 的进程递归子树（含 uv 孙）。"""
        seen: set[int] = set()
        targets: list[int] = []
        if self._pid is not None:
            targets.append(self._pid)
        for pid in self._matching_listener_pids():
            if pid not in seen:
                targets.append(pid)
                seen.add(pid)
        for pid in targets:
            try:
                self._terminate_tree(pid)
            except Exception:  # noqa: BLE001
                logger.warning("清理受管 ComfyUI 进程树失败 pid=%s", pid, exc_info=True)

    def stop(self) -> RuntimeSnapshot:
        current = self._recompute_state()
        if self._state == STATE_RUNNING_EXTERNAL:
            raise EngineNotOwned()
        # 既无受管记录、端口也健康但非 managed_active → 视为已外部停止，幂等返回
        if not self._managed_active and self._pid is None and not self._starting:
            return self._snapshot(current)

        self._state = STATE_STOPPING
        try:
            self._cleanup_managed_tree()
        finally:
            self._clear_record(keep_active=False)
        # 复核端口已释放
        probe = self._probe()
        self._state = STATE_STOPPED if not probe.online else STATE_RUNNING_MANAGED
        return self._snapshot(probe)

    def restart(self) -> RuntimeSnapshot:
        current = self._recompute_state()
        if self._state == STATE_RUNNING_EXTERNAL:
            raise EngineNotOwned()
        if self._pid is not None or self._managed_active or self._starting:
            self._state = STATE_STOPPING
            try:
                self._cleanup_managed_tree()
            finally:
                self._clear_record(keep_active=False)
            self._state = STATE_STOPPED
        return self.start()


# =====================================================================================
# Phase 0.14 Runtime Closure：ControlHub 生产适配器（mode=controlhub，默认）
# =====================================================================================
#
# 生产模式下，ComfyUI 生命周期的唯一 owner 是 ControlHub 官方 lifecycle CLI。
# EngineRuntimeService（上方）保留为 mode=direct 的开发适配器（scripts/dev 使用），
# 绝不删除；但生产默认不走 Popen / psutil 杀树。
#
# 合同冻结（P0）：
#   - Engine Runtime 的 integration_id 永远是 ``comfyui``（127.0.0.1:8188）；
#   - 严禁 EngineRuntimeService / 本适配器对 ``nsfw-studio-v2`` 做 start/stop/restart
#     （nsfw-studio-v2 = Studio 后端 8000，其生命周期归一键停止脚本 / request-shutdown，
#       与生图引擎按钮无关）。

#: ControlHub CLI 解释器 / data_root 机器默认（任务书冻结；仅代码常量，公共 config.yaml 不含）
DEFAULT_CONTROLHUB_PYTHON = r"D:\control-hub\.venv\Scripts\python.exe"
DEFAULT_CONTROLHUB_DATA_ROOT = r"C:\Users\30566\AppData\Local\AIHomeControlHub\data"


class ControlHubEngineRuntime:
    """生产模式适配器：ComfyUI 生命周期一律委托 ControlHub lifecycle CLI（id=comfyui）。

    与 :class:`EngineRuntimeService` 对外同构（``status/start/stop/restart`` → RuntimeSnapshot），
    但绝不 Popen、绝不 psutil 终止进程树；真实进程托管由 ControlHub carrier / 计划任务负责。
    所有 CLI 调用经可 monkeypatch 的 ``_invoke`` seam，测试 hermetic。
    """

    def __init__(self, settings: Settings) -> None:
        from app.services.controlhub_lifecycle import (
            ControlHubLifecycleClient,
            ENGINE_INTEGRATION_ID,
            STUDIO_INTEGRATION_ID,
        )

        cfg = settings.engine_runtime or {}
        self.host = str(cfg.get("host", DEFAULT_HOST))
        self.port = int(cfg.get("port", FIXED_PORT))

        # 合同：engine integration_id 默认 comfyui，绝不能是 nsfw-studio-v2
        self.integration_id = str(cfg.get("integration_id", ENGINE_INTEGRATION_ID))
        if self.integration_id == STUDIO_INTEGRATION_ID:
            raise RuntimeError(
                "EngineRuntime 合同错误：engine integration_id 不得为 nsfw-studio-v2（应为 comfyui）"
            )

        ch_cfg = getattr(settings, "controlhub", {}) or {}
        python_exe = str(ch_cfg.get("python_exe") or DEFAULT_CONTROLHUB_PYTHON)
        data_root = str(ch_cfg.get("data_root") or DEFAULT_CONTROLHUB_DATA_ROOT)
        self._client = ControlHubLifecycleClient(python_exe, data_root)
        self._status_lock = threading.Lock()
        self._status_cached: tuple[float, RuntimeSnapshot] | None = None

        logs_dir = settings.storage.data_root / "logs" / "engine"
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.log_location = str(logs_dir / "comfyui-managed.log")

    # ===== seam（测试 monkeypatch） =====

    def _invoke(self, action: str):
        """调用 ControlHub CLI（seam）。返回 LifecycleResult。"""
        if action == "status":
            return self._client.invoke(action, self.integration_id)
        # 只复用观察快照；生命周期动作仍每次进入官方CLI，前后均失效缓存。
        with self._status_lock:
            self._status_cached = None
        try:
            return self._client.invoke(action, self.integration_id)
        finally:
            with self._status_lock:
                self._status_cached = None

    # ===== 状态映射 =====

    def _snap(self, state: str, owned: bool, detail: str, *, version: str = "") -> RuntimeSnapshot:
        return RuntimeSnapshot(
            state=state,
            host=self.host,
            port=self.port,
            owned=owned,
            pid=None,
            started_at=None,
            detail=detail,
            log_location=self.log_location,
            health={
                "online": state == STATE_RUNNING_MANAGED,
                "engine_name": "comfyui",
                "engine_version": version,
            },
        )

    def _unapproved_detail(self) -> str:
        return f"ComfyUI integration({self.integration_id}) 未注册/未批准（待第二阶段 ControlHub 接入）"

    def status(self) -> RuntimeSnapshot:
        # 同一实例并发读取合并；三秒后重新核查，不建立第二套运行事实。
        with self._status_lock:
            if self._status_cached is not None and time.monotonic() < self._status_cached[0]:
                return self._status_cached[1]
            snapshot = self._read_status()
            self._status_cached = (time.monotonic() + 3.0, snapshot)
            return snapshot

    def _read_status(self) -> RuntimeSnapshot:
        res = self._invoke("status")
        st = res.state
        if st == "online":
            return self._snap(STATE_RUNNING_MANAGED, True,
                              f"ComfyUI 经 ControlHub 运行中 @ {self.host}:{self.port}", version="")
        if st == "degraded":
            return self._snap(STATE_RUNNING_MANAGED, True,
                              f"ComfyUI 运行中（degraded）@ {self.host}:{self.port}")
        if st == "offline":
            return self._snap(STATE_STOPPED, False, "ComfyUI 未运行（ControlHub offline）")
        if res.is_unapproved:
            return self._snap(STATE_ERROR, False, self._unapproved_detail())
        return self._snap(STATE_STOPPED, False, f"ComfyUI 状态未知（{res.reason or st or 'unknown'}）")

    def start(self) -> RuntimeSnapshot:
        res = self._invoke("start")
        if res.ok:
            return self.status()
        if res.is_port_conflict:
            raise EnginePortConflict()
        if res.state == "timed_out":
            return self._snap(STATE_STARTING, True,
                              "ComfyUI 启动超时，仍在进行（ControlHub 冷启约数分钟）")
        if res.is_unapproved:
            return self._snap(STATE_ERROR, False, self._unapproved_detail())
        return self._snap(STATE_ERROR, False,
                          f"ComfyUI 启动失败：{res.reason or res.state or 'unknown'}")

    def stop(self) -> RuntimeSnapshot:
        res = self._invoke("stop")
        if res.ok:
            return self._snap(STATE_STOPPED, False, "ComfyUI 已停止（ControlHub）")
        if res.is_unapproved:
            # 未注册：本就不存在，视为已停（幂等）
            return self._snap(STATE_STOPPED, False, "ComfyUI integration 未注册，无需停止")
        return self._snap(STATE_ERROR, False,
                         f"ComfyUI 停止失败：{res.reason or res.state or 'unknown'}")

    def restart(self) -> RuntimeSnapshot:
        res = self._invoke("restart")
        if res.ok:
            return self.status()
        if res.is_port_conflict:
            raise EnginePortConflict()
        if res.state == "timed_out":
            return self._snap(STATE_STARTING, True, "ComfyUI 重启超时，仍在进行（ControlHub）")
        if res.is_unapproved:
            return self._snap(STATE_ERROR, False, self._unapproved_detail())
        return self._snap(STATE_ERROR, False,
                          f"ComfyUI 重启失败：{res.reason or res.state or 'unknown'}")


def create_engine_runtime(settings: Settings):
    """按 config.engine_runtime.mode 选择适配器（生产默认 controlhub）。

    - ``controlhub``（默认）：ComfyUI 生命周期委托官方 CLI（id=comfyui）；
    - ``direct``：保留 v0.13.2 直接 Popen + uv 桩归属 + 健康探测/自恢复实现（仅 scripts/dev）。
    """
    from app.services.controlhub_lifecycle import MODE_CONTROLHUB, MODE_DIRECT

    cfg = settings.engine_runtime or {}
    mode = str(cfg.get("mode", MODE_CONTROLHUB)).strip().lower()
    if mode == MODE_DIRECT:
        return EngineRuntimeService(settings)
    # 默认（含未识别值）走生产 controlhub，绝不静默回退到 Popen
    return ControlHubEngineRuntime(settings)
