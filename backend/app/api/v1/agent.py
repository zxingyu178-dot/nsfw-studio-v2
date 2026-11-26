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
from app.core.errors import (
    ForbiddenError,
    TooManyRequestsError,
    UnauthorizedError,
    UnprocessableError,
)
from app.engine.base import EngineBindingRef
from app.engine.release import ensure_modules_released
from app.schemas.agent import AgentJobRequest
from app.schemas.job import JobResponse, job_response
from app.schemas.workbench import WorkbenchSnapshotModel
from app.services import agent_service, job_service, prompt_service
from app.services.lora_validation_service import validate_task_loras
from app.services.model_registry_service import ModelRegistryService
from app.services.runtime_preflight_service import run_preflight

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


@router.get(
    "/agent/capabilities",
    summary="Agent/AI 能力发现：模块、底模、LoRA 与参数边界",
)
def agent_capabilities(request: Request) -> dict:
    _require_token(request)
    from app.api.v1.modules import list_modules

    settings = request.app.state.settings
    modules = list_modules(request)
    adapter = request.app.state.adapter
    models = []
    loras = []
    available_models = getattr(adapter, "available_checkpoint_names", None)
    if callable(available_models):
        models = sorted(available_models() or [])
    available_loras = getattr(adapter, "available_lora_names", None)
    if callable(available_loras):
        loras = sorted(available_loras() or [])
    engine_cfg = (settings.workflow.raw or {}).get("engine") or {}
    profiles = ModelRegistryService(settings).checkpoint_sampling_profiles()
    return {
        "default_module_id": engine_cfg.get("module_id"),
        "modules": modules,
        "models": models,
        "sampling_profiles": {
            name: profiles[name] for name in models if name in profiles
        },
        "loras": loras,
        "limits": {
            "width": {"min": 64, "max": 4096},
            "height": {"min": 64, "max": 4096},
            "count": {"min": 1, "max": 64},
            "loras": {"max": 2, "strength_min": -2.0, "strength_max": 2.0},
            "steps": {"min": 1, "max": 100},
            "cfg": {"min": 1.0, "max": 20.0},
            "denoise": {"min": 0.0, "max": 1.0},
        },
    }


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
    extra = body.model_extra or {}
    if "upscale" in extra:
        raise UnprocessableError(
            "upscale 参数已下线：产品不再提供 4x 高清放大；请移除该字段后重试",
            code="AGENT_UPSCALE_REMOVED",
        )
    disk = check_disk_space(request)
    settings = request.app.state.settings

    # W1.2-B/C：先解析实际工作流（不传 module_id = 服务器默认）→ 正式放行 → 能力校验。
    # 任一检查失败都在 Prompt 关联（commit=False）与 Job 创建之前返回，不产生副作用。
    workflow_modules = agent_service.resolve_agent_workflow_modules(
        settings,
        body.module_id,
        module_version=body.module_version,
        binding_version=body.binding_version,
    )
    config: dict = {}
    if body.use_recommended_sampling:
        if not body.model:
            raise UnprocessableError(
                "use_recommended_sampling=true 时必须同时指定 model",
                code="RECOMMENDED_SAMPLING_MODEL_REQUIRED",
            )
        profile = ModelRegistryService(settings).checkpoint_sampling_profiles().get(body.model)
        if not profile:
            raise UnprocessableError(
                f"底模未登记推荐采样参数: {body.model}",
                code="RECOMMENDED_SAMPLING_NOT_FOUND",
                details={"model": body.model},
            )
        # 推荐值作为基线，下方显式 params 覆盖，模型/LoRA 原样保留。
        config.update({
            key: profile[key]
            for key in ("steps", "cfg", "sampler_name", "scheduler", "denoise")
            if key in profile
        })
    if body.model:
        config["model"] = body.model
    if body.loras:
        config["loras"] = [item.model_dump() for item in body.loras]
    if body.params:
        config.update(body.params.model_dump(exclude_none=True))
    if config:
        workflow_modules[0]["config"] = config

    # 任务级参数必须由所选 binding 声明为可注入，否则在创建 Job 前拒绝。
    if config:
        primary = workflow_modules[0]
        adapter = request.app.state.adapter
        load_binding = getattr(adapter, "load_binding", None)
        if callable(load_binding):
            _workflow, binding, _workflow_hash, _binding_hash = load_binding(
                EngineBindingRef(
                    module_id=str(primary.get("module_id")),
                    module_version=str(primary.get("module_version")),
                    provider=str(primary.get("provider")),
                    binding_version=str(primary.get("binding_version")),
                )
            )
            inputs = binding.get("inputs") or {}
            for key in ("model", "steps", "cfg", "sampler_name", "scheduler", "denoise"):
                if key in config and key not in inputs:
                    raise UnprocessableError(
                        f"当前 binding {primary.get('binding_version')} 不支持任务级参数 {key}",
                        code="BINDING_PARAM_UNSUPPORTED",
                        details={"binding_version": primary.get("binding_version"), "parameter": key},
                    )
            # face_detailer 由 adapter 按节点类型应用（v15 binding Hash 保持冻结），
            # 这里只校验目标工作流确实包含 FaceDetailer。
            if "face_detailer" in config:
                has_face_detailer = any(
                    isinstance(node, dict) and node.get("class_type") == "FaceDetailer"
                    for node in (_workflow or {}).values()
                )
                if not has_face_detailer:
                    raise UnprocessableError(
                        f"当前 binding {primary.get('binding_version')} 不支持任务级参数 face_detailer",
                        code="BINDING_PARAM_UNSUPPORTED",
                        details={
                            "binding_version": primary.get("binding_version"),
                            "parameter": "face_detailer",
                        },
                    )
        if body.model:
            available_models = getattr(adapter, "available_checkpoint_names", None)
            if callable(available_models):
                names = available_models()
                if names is not None and body.model not in names:
                    raise UnprocessableError(
                        f"底模不存在: {body.model}",
                        code="MODEL_NOT_FOUND",
                        details={"model": body.model},
                    )

    ensure_modules_released(workflow_modules)
    validate_task_loras(request.app.state.adapter, workflow_modules)
    agent_service.validate_agent_primary(settings, workflow_modules)
    # W2.0：运行环境前置检测（在 Prompt 关联与 Job 创建之前）
    preflight = run_preflight(settings, request.app.state.adapter, workflow_modules)

    # 快照必须记录最终实际使用的模块身份（不能记录空的默认选择）。
    snapshot_modules = [
        {
            "module_id": module.get("module_id"),
            "module_version": module.get("module_version"),
            "provider": module.get("provider"),
            "binding_version": module.get("binding_version"),
            "workflow_hash": module.get("workflow_hash"),
            "binding_hash": module.get("binding_hash"),
            "config": module.get("config") or {},
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
            engine_version=str((preflight.get("engine") or {}).get("version") or "") or None,
        )
    except Exception:
        session.rollback()
        raise
    response = job_response(job)
    response.idempotent_replay = not created
    response.disk_space = disk
    return response
