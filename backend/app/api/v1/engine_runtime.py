"""受管 ComfyUI 运行时 API（冻结契约，前端据此开发）。

    GET  /api/v1/engine/runtime
    POST /api/v1/engine/runtime/start
    POST /api/v1/engine/runtime/stop
    POST /api/v1/engine/runtime/restart

返回体（start 失败也返回 200 且 state=ERROR，便于统一渲染）::

    {"state","host","port","owned","pid","started_at","detail","log_location",
     "health":{"online","engine_name","engine_version"}}

错误（统一信封 {"error":{"code","message"}}）::
    external stop/restart → 409 ENGINE_NOT_OWNED
    PORT_CONFLICT start   → 409 ENGINE_PORT_CONFLICT

阻塞型（subprocess/psutil）操作经 asyncio.to_thread 包装，不阻塞事件循环。
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.v1.jobs import resolve_requested_modules
from app.services.runtime_preflight_service import RuntimePreflightService

logger = logging.getLogger(__name__)

router = APIRouter()


class PreflightRequest(BaseModel):
    """W2.0：工作台当前选择的模块（只传 ID，服务端重新解析真实身份）。"""

    module_ids: list[str] = Field(min_length=1, max_length=8)


@router.get("/engine/runtime", summary="受管 ComfyUI 运行时状态")
async def get_runtime(request: Request) -> dict:
    svc = request.app.state.engine_runtime
    snapshot = await asyncio.to_thread(svc.status)
    return snapshot.to_dict()


@router.post("/engine/runtime/start", summary="启动受管 ComfyUI（幂等）")
async def start_runtime(request: Request) -> dict:
    svc = request.app.state.engine_runtime
    # EnginePortConflict 由全局 AppError handler 转 409
    snapshot = await asyncio.to_thread(svc.start)
    return snapshot.to_dict()


@router.post("/engine/runtime/stop", summary="停止受管 ComfyUI（仅 owned）")
async def stop_runtime(request: Request) -> dict:
    svc = request.app.state.engine_runtime
    # EngineNotOwned 由全局 AppError handler 转 409
    snapshot = await asyncio.to_thread(svc.stop)
    return snapshot.to_dict()


@router.post("/engine/runtime/restart", summary="重启受管 ComfyUI（仅 owned）")
async def restart_runtime(request: Request) -> dict:
    svc = request.app.state.engine_runtime
    snapshot = await asyncio.to_thread(svc.restart)
    return snapshot.to_dict()


@router.post("/engine/preflight", summary="W2.0 运行环境前置检测（READY/BLOCKED/UNKNOWN）")
def preflight(request: Request, body: PreflightRequest) -> dict:
    """重新解析真实工作流身份后检测引擎、Binding、节点、模型与版本。

    该接口只提供诊断结果；实际提交仍由 /jobs 与 /agent/jobs 的服务端 Gate 再次检测。
    """
    settings = request.app.state.settings
    modules = resolve_requested_modules(
        settings, [{"module_id": module_id} for module_id in body.module_ids]
    )
    service = RuntimePreflightService(settings, request.app.state.adapter)
    return service.check_modules(modules)
