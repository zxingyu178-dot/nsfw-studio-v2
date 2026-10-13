"""System Status API（Phase 0.12 Task7）：只读系统/存储/引擎运行时摘要。

    GET /api/v1/system/status

Settings 页升级为"系统与维护中心"的数据来源；只读，绝不返回敏感配置内容。

Phase 0.14 Runtime Closure 另增应用内"停止全部后台"自停桥：

    POST /api/v1/system/request-shutdown

    - 仅回环可用（127.0.0.1 / ::1），外部调用 403；
    - 立即返回 202（{accepted:true,...}）；
    - 后端自身绝不杀自己：以一次性 detached 方式拉起 shutdown helper
      （scripts/runtime/shutdown_helper.ps1），由它延迟 ~500ms 后调用 stop_studio.ps1
      执行完整停止序列；
    - 幂等：已有 pending shutdown 时不重复拉起 helper。
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.errors import ForbiddenError
from app.schemas.system import SystemStatusResponse
from app.services import system_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])

#: 一次性 detached 关机 helper 的相对路径（相对项目根）
SHUTDOWN_HELPER_RELPATH = ("scripts", "runtime", "shutdown_helper.ps1")

#: Windows detached 启动标志（独立进程组 + 无窗口；不随后端退出被杀）
_DETACHED_FLAGS = (
    getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
)


def _request_is_loopback(request: Request) -> bool:
    """判断请求是否来自回环（seam，测试可 monkeypatch）。"""
    client = request.client
    if client is None:
        return False
    return client.host in ("127.0.0.1", "::1", "localhost")


def _resolve_shutdown_helper(settings) -> str:
    """定位 shutdown_helper.ps1（项目根/scripts/runtime/）。"""
    project_root = Path(settings.config_dir).resolve().parent
    return str(project_root.joinpath(*SHUTDOWN_HELPER_RELPATH))


def _launch_shutdown_helper(helper_path: str) -> None:
    """detached 拉起关机 helper（seam，测试 monkeypatch；真实实现绝不被测试调用）。

    后端自身不杀自己：helper 是一次性、非长期服务、非第二 lifecycle owner，
    仅作为"从应用内调用官方 lifecycle CLI 停止序列"的桥。
    """
    subprocess.Popen(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", helper_path,
        ],
        creationflags=_DETACHED_FLAGS,
        close_fds=True,
    )


@router.get("/status", response_model=SystemStatusResponse,
            summary="只读系统状态摘要（版本/路径/磁盘/图片计数/最新迁移/引擎运行时）")
def system_status(request: Request, session: Session = Depends(get_session)) -> SystemStatusResponse:
    engine_runtime = getattr(request.app.state, "engine_runtime", None)
    summary = system_service.collect_system_status(
        session, request.app.state.settings, engine_runtime
    )
    return SystemStatusResponse(**summary)


@router.post("/request-shutdown", status_code=202,
             summary="请求一键停止整个 Studio（仅回环；202 后由 detached helper 执行）")
def request_shutdown(request: Request) -> dict:
    if not _request_is_loopback(request):
        raise ForbiddenError("request-shutdown 仅允许本机回环调用")

    # 幂等：pending 状态挂在 app.state（每应用实例独立，测试天然隔离）
    already = bool(getattr(request.app.state, "shutdown_pending", False))
    request.app.state.shutdown_pending = True

    if already:
        logger.info("request-shutdown 已在进行中，幂等返回（不重复拉起 helper）")
        return {"accepted": True, "already_pending": True,
                "message": "停止序列已在进行中"}

    helper = _resolve_shutdown_helper(request.app.state.settings)
    logger.info("request-shutdown 接受，detached 拉起关机 helper: %s", helper)
    try:
        _launch_shutdown_helper(helper)
    except OSError:
        # helper 拉起失败不影响 202 已承诺；记录 warning，桌面 stop 脚本仍可兜底
        logger.warning("detached 拉起关机 helper 失败: %s", helper, exc_info=True)
        return {"accepted": True, "already_pending": False,
                "helper": helper, "helper_launched": False,
                "message": "已接受停止请求，但 helper 拉起失败，请使用桌面停止快捷方式"}

    return {"accepted": True, "already_pending": False,
            "helper": helper, "helper_launched": True,
            "message": "已接受停止请求，正在执行停止序列"}
