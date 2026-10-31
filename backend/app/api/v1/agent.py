"""Agent / AI 提交端点（Phase 0.34）：给豆包/本地 Agent 的安全提交入口。

安全模型：
- 默认**关闭**：只有配置了 token（`configs/config.local.yaml` 的 `agent.token`
  或环境变量 `NSFW_STUDIO_AGENT_TOKEN`）才启用；
- 必须 `Authorization: Bearer <token>`；token 只存在本机私有配置，不写日志；
- 每分钟限速（默认 30 次，`agent.rate_limit_per_min` / `NSFW_STUDIO_AGENT_RATE_LIMIT`）；
- 8000 仍固定 loopback（`app.host=127.0.0.1`），不对外暴露；远程 AI 请通过安全隧道 + token，
  绝不允许直接 0.0.0.0 暴露；
- 复用 JobService 的完整校验/幂等（client_request_id），不做第二条执行链。

普通 UI 继续使用 `/api/v1/jobs`；本端点只提供 AI 友好的简化契约。
"""
from __future__ import annotations

import hashlib
import os
import secrets
import threading
import time
import uuid
from collections import deque

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.v1.jobs import check_disk_space
from app.core.config import ENV_AGENT_RATE_LIMIT, ENV_AGENT_TOKEN
from app.core.errors import ForbiddenError, TooManyRequestsError, UnauthorizedError
from app.engine.release import ensure_modules_released
from app.schemas.agent import AgentJobRequest
from app.schemas.job import JobResponse, job_response
from app.schemas.workbench import WorkbenchSnapshotModel
from app.services import agent_service, job_service, prompt_service

router = APIRouter(tags=["agent"])

_RATE_BUCKETS: dict[str, deque[float]] = {}
_RATE_LOCK = threading.Lock()
_RATE_WINDOW_SECONDS = 60.0
_DEFAULT_RATE_LIMIT = 30


def _agent_config(request: Request) -> tuple[str, int]:
    """读取 token 与限速（环境变量 > config.local `agent` 段 > 默认）。"""
    settings = request.app.state.settings
    cfg = getattr(settings, "agent", {}) or {}
    token = (os.environ.get(ENV_AGENT_TOKEN) or cfg.get("token") or "").strip()
    raw_limit = os.environ.get(ENV_AGENT_RATE_LIMIT) or cfg.get("rate_limit_per_min") or _DEFAULT_RATE_LIMIT
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        limit = _DEFAULT_RATE_LIMIT
    return token, max(0, limit)


def _require_token(request: Request) -> str:
    token, limit = _agent_config(request)
    if not token:
        raise ForbiddenError(
            "Agent 提交未启用：请在 configs/config.local.yaml 配置 agent.token（或设置环境变量 "
            "NSFW_STUDIO_AGENT_TOKEN）后重启 Studio。",
            code="AGENT_API_DISABLED",
        )
    scheme, _, provided = request.headers.get("Authorization", "").partition(" ")
    provided = provided.strip()
    if scheme.lower() != "bearer" or not provided:
        raise UnauthorizedError("缺少 Bearer token（Authorization: Bearer <token>）", code="AGENT_TOKEN_MISSING")
    if not secrets.compare_digest(provided, token):
        raise UnauthorizedError("Agent token 无效", code="AGENT_TOKEN_INVALID")

    # 按 token 摘要限速，内存中不保存 token 明文。
    if limit > 0:
        key = hashlib.sha256(provided.encode("utf-8")).hexdigest()
        now = time.monotonic()
        with _RATE_LOCK:
            bucket = _RATE_BUCKETS.setdefault(key, deque())
            while bucket and now - bucket[0] >= _RATE_WINDOW_SECONDS:
                bucket.popleft()
            if len(bucket) >= limit:
                raise TooManyRequestsError(
                    f"Agent 提交过于频繁（上限 {limit} 次/分钟），请稍后再试",
                    code="AGENT_RATE_LIMITED",
                )
            bucket.append(now)
    return provided


@router.post(
    "/agent/jobs",
    response_model=JobResponse,
    status_code=201,
    summary="Agent/AI 提交生成任务（Bearer token；默认关闭）",
)
def submit_agent_job(
    request: Request,
    body: AgentJobRequest,
    session: Session = Depends(get_session),
) -> JobResponse:
    _require_token(request)
    disk = check_disk_space(request)
    settings = request.app.state.settings

    # W1.2-B/C：先解析实际工作流（不传 module_id = 服务器默认）→ 正式放行 → 能力校验。
    # 任一检查失败都在 Prompt 关联（commit=False）与 Job 创建之前返回，不产生副作用。
    workflow_modules = agent_service.resolve_agent_workflow_modules(
        settings, body.module_id, upscale=body.upscale
    )
    ensure_modules_released(workflow_modules)
    agent_service.validate_agent_primary(settings, workflow_modules)

    # 快照必须记录最终实际使用的模块身份（不能记录空的默认选择）。
    snapshot_modules = [
        {
            "module_id": module.get("module_id"),
            "module_version": module.get("module_version"),
            "provider": module.get("provider"),
            "binding_version": module.get("binding_version"),
            "workflow_hash": module.get("workflow_hash"),
            "binding_hash": module.get("binding_hash"),
        }
        for module in workflow_modules
    ]
    snapshot_model = WorkbenchSnapshotModel(
        prompt_mode="full",
        full_prompt=body.prompt,
        negative_prompt=body.negative_prompt,
        generation_mode="text",
        width=body.width,
        height=body.height,
        count=body.count,
        seed_mode="fixed" if body.seed is not None else "random",
        seed=body.seed,
        workflow_modules=snapshot_modules,
    )
    snapshot = snapshot_model.model_dump()
    # W1.2.1：Prompt 与 Job 同一事务；此处只 flush（commit=False），
    # 由 JobService 创建成功后统一提交；任何失败由下方 rollback。
    prompt_service.attach_ai_prompt(session, snapshot, commit=False)

    try:
        job, created = job_service.create_job(
            session,
            source="agent",
            client_request_id=body.client_request_id or f"agent_{uuid.uuid4().hex[:16]}",
            snapshot=snapshot,
            queue_mode=body.queue_mode,
            workflow_modules=workflow_modules,
            job_kind="generate",
        )
    except Exception:
        session.rollback()
        raise
    response = job_response(job)
    response.idempotent_replay = not created
    response.disk_space = disk
    return response
