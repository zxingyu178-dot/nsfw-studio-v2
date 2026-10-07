"""Prompt API：只做请求解析 → 调用 Service → 返回 Response（规范 §三十三）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.prompt import (
    ComposeRequest,
    ComposeResponse,
    PromptCreateRequest,
    PromptListResponse,
    PromptMetaUpdateRequest,
    PromptResponse,
    PromptVersionCreateRequest,
    PromptVersionResponse,
    prompt_response,
    prompt_version_response,
)
from app.services import prompt_service
from app.services.prompt_composer import compose_structured

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.post("/compose", response_model=ComposeResponse, summary="结构化 Prompt 合成预览（与保存规则一致）")
def compose_prompt(request: ComposeRequest) -> ComposeResponse:
    if request.mode == "structured":
        composed = compose_structured(request.structured.model_dump())
    else:
        composed = request.positive_prompt
    return ComposeResponse(composed_prompt=composed)


@router.get("", response_model=PromptListResponse, summary="Prompt 列表")
def list_prompts(
    search: str | None = Query(default=None),
    favorite: bool | None = Query(default=None),
    archived: bool | None = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> PromptListResponse:
    items, total = prompt_service.list_prompts(
        session, search=search, favorite=favorite, archived=archived, limit=limit, offset=offset
    )
    return PromptListResponse(
        items=[
            prompt_response(prompt, prompt_service.get_current_version(session, prompt))
            for prompt in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=PromptResponse, status_code=201, summary="创建 Prompt（+v1）")
def create_prompt(request: PromptCreateRequest, session: Session = Depends(get_session)) -> PromptResponse:
    prompt = prompt_service.create_prompt(
        session,
        name=request.name,
        mode=request.mode,
        positive_prompt=request.positive_prompt,
        negative_prompt=request.negative_prompt,
        structured=request.structured.model_dump(),
        favorite=request.favorite,
    )
    return prompt_response(prompt, prompt_service.get_current_version(session, prompt))


@router.get("/{prompt_id}", response_model=PromptResponse, summary="Prompt 详情")
def get_prompt(prompt_id: str, session: Session = Depends(get_session)) -> PromptResponse:
    prompt = prompt_service.get_prompt(session, prompt_id)
    return prompt_response(prompt, prompt_service.get_current_version(session, prompt))


@router.patch("/{prompt_id}", response_model=PromptResponse, summary="修改元数据（不产生内容版本）")
def update_prompt_meta(
    prompt_id: str, request: PromptMetaUpdateRequest, session: Session = Depends(get_session)
) -> PromptResponse:
    prompt = prompt_service.update_prompt_meta(session, prompt_id, name=request.name, favorite=request.favorite)
    return prompt_response(prompt, prompt_service.get_current_version(session, prompt))


@router.post("/{prompt_id}/versions", response_model=PromptVersionResponse, status_code=201, summary="新增内容版本")
def add_prompt_version(
    prompt_id: str, request: PromptVersionCreateRequest, session: Session = Depends(get_session)
) -> PromptVersionResponse:
    version, _ = prompt_service.add_prompt_version(
        session,
        prompt_id,
        mode=request.mode,
        positive_prompt=request.positive_prompt,
        negative_prompt=request.negative_prompt,
        structured=request.structured.model_dump(),
    )
    return prompt_version_response(version)


@router.get("/{prompt_id}/versions", response_model=list[PromptVersionResponse], summary="版本历史")
def list_prompt_versions(prompt_id: str, session: Session = Depends(get_session)) -> list[PromptVersionResponse]:
    return [prompt_version_response(version) for version in prompt_service.list_versions(session, prompt_id)]


@router.post(
    "/{prompt_id}/versions/{version_id}/restore",
    response_model=PromptVersionResponse,
    status_code=201,
    summary="恢复旧版本（复制为新最新版，指针不倒退）",
)
def restore_prompt_version(
    prompt_id: str, version_id: str, session: Session = Depends(get_session)
) -> PromptVersionResponse:
    version = prompt_service.restore_prompt_version(session, prompt_id, version_id)
    return prompt_version_response(version)


@router.post("/{prompt_id}/archive", response_model=PromptResponse, summary="归档（软删除）")
def archive_prompt(prompt_id: str, session: Session = Depends(get_session)) -> PromptResponse:
    prompt = prompt_service.set_archived(session, prompt_id, archived=True)
    return prompt_response(prompt, prompt_service.get_current_version(session, prompt))


@router.post("/{prompt_id}/restore", response_model=PromptResponse, summary="从归档恢复")
def restore_prompt(prompt_id: str, session: Session = Depends(get_session)) -> PromptResponse:
    prompt = prompt_service.set_archived(session, prompt_id, archived=False)
    return prompt_response(prompt, prompt_service.get_current_version(session, prompt))
