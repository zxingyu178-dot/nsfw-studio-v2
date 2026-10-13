"""ControlHub 官方 lifecycle CLI 客户端（Phase 0.14 Runtime Closure）。

封装对官方 CLI 的子进程调用，命令形态（冻结）::

    <python_exe> -m control_hub.lifecycle_cli <command> <integration_id> --data-root <data_root>

设计红线（务必遵守）：
- 解释器 / 模块 / 动作 / integration_id / ``--data-root`` 全部来自配置，绝不在调用点散写
  ``subprocess``；所有真实进程调用经 :meth:`ControlHubLifecycleClient._run` 这一处 seam，
  测试全部 monkeypatch 它，本阶段绝不真实起进程；
- 命令顺序硬冻结：``--data-root`` 必须出现在 ``<integration_id>`` **之后**。
  ``lifecycle_cli.py`` 把 ``--data-root`` 定义在【子解析器】上（L233-237），主解析器没有该参数，
  放子命令之前会报 ``unrecognized arguments``；
- CLI 只对 approved 集成生效；未知 / 未批准 integration 返回退出码 2（``unknown_integration``）；
- 退出码语义（见可行性报告 A.2）::
    0 = status 读成功 / 动作 succeeded（含幂等 already_in_target_state）；
    1 = blocked / timed_out / failed（含 reason=port_conflict）；
    2 = 参数错 / 非白名单 data-root / 未知或未批准集成。
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: 官方 CLI 模块名（源码 venv 模式调用）
MODULE = "control_hub.lifecycle_cli"

#: 子命令（与官方 lifecycle_cli 同构：status/start/stop/restart）
ACTION_STATUS = "status"
ACTION_START = "start"
ACTION_STOP = "stop"
ACTION_RESTART = "restart"
_ACTIONS = frozenset({ACTION_STATUS, ACTION_START, ACTION_STOP, ACTION_RESTART})

#: 退出码语义
EXIT_OK = 0
EXIT_ACTION_FAILED = 1   # blocked / timed_out / failed / port_conflict
EXIT_BAD_REQUEST = 2     # 参数错 / 非白名单 data-root / 未知或未批准集成

#: config.engine_runtime.mode 取值
MODE_CONTROLHUB = "controlhub"
MODE_DIRECT = "direct"

#: 合同冻结的 integration_id
#: Engine Runtime（生图引擎）永远只操作 ComfyUI；Studio 后端自身才用 nsfw-studio-v2。
ENGINE_INTEGRATION_ID = "comfyui"
STUDIO_INTEGRATION_ID = "nsfw-studio-v2"


@dataclass
class LifecycleResult:
    """一次 CLI 调用的归一化结果（JSON 解析 + 退出码）。"""

    action: str
    integration_id: str
    exit_code: int
    state: str          # CLI 返回 JSON 的 state（succeeded/blocked/timed_out/failed/online/offline/degraded/unknown）
    reason: str         # reason（port_conflict/completed/unknown_integration/cli_timeout/...）
    service_state: str  # service_state（如有）
    raw: str            # 原始 stdout（便于排障）

    @property
    def ok(self) -> bool:
        return self.exit_code == EXIT_OK

    @property
    def is_unapproved(self) -> bool:
        """未知 / 未批准 integration（退出码 2 或 reason=unknown_integration）。"""
        return self.exit_code == EXIT_BAD_REQUEST or "unknown_integration" in self.reason

    @property
    def is_port_conflict(self) -> bool:
        return "port_conflict" in self.reason


class ControlHubLifecycleClient:
    """对官方 lifecycle CLI 的薄封装（唯一 subprocess seam 在此）。"""

    def __init__(self, python_exe: str, data_root: str, timeout_s: float = 60.0) -> None:
        if not python_exe:
            raise ValueError("ControlHubLifecycleClient 需要 python_exe（官方 CLI 解释器）")
        if not data_root:
            raise ValueError("ControlHubLifecycleClient 需要 data_root（安装版 registry 目录）")
        self.python_exe = python_exe
        self.data_root = data_root
        self.timeout_s = float(timeout_s)

    def build_argv(self, action: str, integration_id: str) -> list[str]:
        """构造冻结顺序的命令行：``-m MODULE action id --data-root path``。"""
        if action not in _ACTIONS:
            raise ValueError(f"未知 lifecycle 动作: {action!r}")
        if not integration_id:
            raise ValueError("integration_id 不能为空")
        return [
            self.python_exe,
            "-m", MODULE,
            action,
            integration_id,
            "--data-root", self.data_root,
        ]

    def _run(self, argv: list[str]) -> tuple[int, str]:
        """seam：测试用 monkeypatch 替换。默认真实 subprocess；本阶段测试绝不真实调用。

        hermetic 护栏：当 ``NSFW_STUDIO_HERMETIC=1``（conftest 对整个 tests/backend 置位）时，
        默认实现**绝不**起真实进程，直接返回可解析的离线占位输出，保证应用级测试
        （``create_app`` + lifespan）不触碰真实 CLI / registry。专项测试 monkeypatch 本方法后
        完全绕开此护栏，自行控制返回值。
        """
        if os.environ.get("NSFW_STUDIO_HERMETIC") == "1":
            return EXIT_OK, '{"state":"offline","reason":"hermetic_short_circuit"}'
        kwargs: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "timeout": self.timeout_s,
        }
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.run(argv, **kwargs)
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out

    def invoke(self, action: str, integration_id: str) -> LifecycleResult:
        """执行动作并返回归一化结果（永不抛异常——失败都映射为结果状态）。"""
        argv = self.build_argv(action, integration_id)
        logger.info("ControlHub lifecycle CLI: %s %s", action, integration_id)
        try:
            exit_code, out = self._run(argv)
        except subprocess.TimeoutExpired:
            return LifecycleResult(
                action, integration_id, EXIT_ACTION_FAILED,
                state="timed_out", reason="cli_timeout", service_state="", raw="",
            )
        except OSError as error:
            logger.warning("lifecycle CLI 调用失败 %s %s: %s", action, integration_id, error)
            return LifecycleResult(
                action, integration_id, EXIT_BAD_REQUEST,
                state="failed", reason=f"spawn_error:{error.__class__.__name__}",
                service_state="", raw="",
            )
        parsed = self._parse_json(out)
        return LifecycleResult(
            action=action, integration_id=integration_id, exit_code=exit_code,
            state=str(parsed.get("state", "") or ""),
            reason=str(parsed.get("reason", "") or ""),
            service_state=str(parsed.get("service_state", "") or ""),
            raw=out.strip(),
        )

    @staticmethod
    def _parse_json(out: str) -> dict[str, Any]:
        """CLI 输出单行 JSON；逐行找第一个能解析为 dict 的 JSON 对象。"""
        for line in out.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if isinstance(data, dict):
                return data
        return {}
