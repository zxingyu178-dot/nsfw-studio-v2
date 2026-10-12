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

logger = logging.getLogger(__name__)

router = APIRouter()


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
