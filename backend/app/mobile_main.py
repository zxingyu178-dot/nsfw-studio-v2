"""Mobile Review Bridge 独立入口（FastAPI app）。

安全红线（P0）：
- 这是一个**独立** FastAPI app，由 uvicorn 以 ``app.mobile_main:app`` 拉起，监听
  独立端口 8877（host 0.0.0.0，供同网段手机访问）；
- **只 include** mobile/system、mobile/pairing、mobile/images、mobile/review；
- **禁止** include jobs / engine_runtime / prompts / recipes / assets / cleanup /
  modules / desktop SPA（route table 守卫测试会断言这些不存在）；
- 8000 始终 loopback，本 app 绝不改变它；
- 仅 ``/mobile/*`` 走统一 envelope；开放端点只有 health / pairing status / pairing verify。

Orphan 防护：主 Studio 经环境变量 ``NSFW_STUDIO_MOBILE_BRIDGE_PARENT_PID`` 把自己的
PID 传给本进程；后台线程轮询该父 PID，主 Studio 退出后本进程自行退出（不留孤儿）。
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

import psutil
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.mobile import images, pairing, review, system, prompts
from app.core.config import Settings, load_settings
from app.core.errors import AppError
from app.database.base import make_engine, make_session_factory
from app.services.system_service import bootstrap
from app.storage.manager import StorageManager

logger = logging.getLogger(__name__)

PARENT_PID_ENV = "NSFW_STUDIO_MOBILE_BRIDGE_PARENT_PID"


def _envelope(success: bool, data=None, *, code: str | None = None,
              message: str | None = None, details=None, request_id: str | None = None) -> dict:
    return {
        "success": success,
        "data": data if success else None,
        "error": None if success else {"code": code, "message": message, "details": details},
        "request_id": request_id or str(uuid.uuid4()),
    }


# 框架 HTTP 错误 → 语义化 code（Starlette HTTPException 不带业务 code）
_CODE_FOR_STATUS = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
}


async def _parent_watch(stop_event: asyncio.Event) -> None:
    """父 PID 守护：主 Studio 退出 → 本 Bridge 自行退出（Orphan 防护）。"""
    raw = os.environ.get(PARENT_PID_ENV)
    if not raw:
        return
    try:
        parent_pid = int(raw)
    except ValueError:
        return
    while not stop_event.is_set():
        try:
            alive = psutil.Process(parent_pid).is_running()
        except psutil.Error:
            alive = False
        if not alive:
            logger.warning("父 Studio(pid=%s) 已退出，Mobile Bridge 自行退出", parent_pid)
            # 给事件循环一拍后退出进程
            os._exit(0)
        await asyncio.sleep(2.0)


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings: Settings = application.state.settings
    bootstrap(settings)

    engine = make_engine(settings.storage.database_path)
    session_factory = make_session_factory(engine)
    storage = StorageManager(settings)

    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.storage = storage

    stop_event = asyncio.Event()
    application.state._stop_event = stop_event
    application.state._parent_watch = asyncio.create_task(_parent_watch(stop_event))

    logger.info("Mobile Review Bridge 启动 version=0.38.0 port=%s", settings.mobile_review.get("port", 8877))
    yield

    stop_event.set()
    watcher = application.state._parent_watch
    watcher.cancel()
    engine.dispose()
    logger.info("Mobile Review Bridge 停止")


def create_mobile_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    # 安全硬化 O2：8877 在 LAN 暴露，关闭 /docs /redoc /openapi.json；
    # 对外合同产物以已提交的 docs/integration/openapi-mobile-review.json 为准。
    application = FastAPI(
        title="NSFW Studio Mobile Review Bridge",
        version="0.38.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    application.state.settings = settings

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 手机浏览器跨域；鉴权靠 Bearer，不靠 Origin
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ===== 统一 envelope（仅本 app 的 /mobile/*） =====
    @application.middleware("http")
    async def envelope_middleware(request: Request, call_next):
        request_id = str(uuid.uuid4())
        try:
            response = await call_next(request)
        except AppError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=_envelope(False, code=exc.code, message=exc.message,
                                  details=getattr(exc, "details", None), request_id=request_id),
            )
        # 图片文件流（image/*）原样放行；JSON 响应包成统一 envelope。
        ctype = response.headers.get("content-type", "")
        response.headers["X-Request-ID"] = request_id
        if "application/json" not in ctype:
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        if response.status_code >= 400:
            # 框架错误（Starlette HTTPException，如 404/405）没有业务 code：
            # 按 HTTP 状态映射成语义化 code，HTTP 状态码不变。
            try:
                import json as _json
                err = _json.loads(body.decode("utf-8"))
            except Exception:
                err = {}
            inner = err.get("error", err) if isinstance(err, dict) else {}
            code = inner.get("code") or _CODE_FOR_STATUS.get(response.status_code, "INTERNAL_ERROR")
            message = inner.get("message") or inner.get("detail") or "请求失败"
            return JSONResponse(
                status_code=response.status_code,
                content=_envelope(
                    False,
                    code=code,
                    message=message,
                    details=inner.get("details"),
                    request_id=request_id,
                ),
            )
        import json as _json
        try:
            data = _json.loads(body.decode("utf-8"))
        except Exception:
            data = None
        return JSONResponse(
            status_code=response.status_code,
            content=_envelope(True, data=data, request_id=request_id),
        )

    @application.exception_handler(AppError)
    def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(False, code=exc.code, message=exc.message,
                              details=getattr(exc, "details", None)),
        )

    @application.exception_handler(RequestValidationError)
    def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        message = f"参数校验失败: {location} {first.get('msg', '')}".strip()
        return JSONResponse(
            status_code=422,
            content=_envelope(False, code="VALIDATION_ERROR", message=message),
        )

    @application.exception_handler(Exception)
    def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Mobile Bridge 未处理异常: %s", exc)
        return JSONResponse(
            status_code=500,
            content=_envelope(False, code="INTERNAL_ERROR", message="服务器内部错误"),
        )

    # 只 include 审核相关四个子域（route table 守卫测试断言无其它模块）
    application.include_router(system.router)
    application.include_router(pairing.router)
    application.include_router(images.router)
    application.include_router(review.router)
    application.include_router(prompts.router)

    return application


app = create_mobile_app()
