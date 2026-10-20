"""Prompt API：只做请求解析 → 调用 Service → 返回 Response（规范 §三十三）。"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.prompt import (
    ComposeRequest,
    ComposeResponse,
    PromptCreateRequest,
    PromptEvaluationCreateRequest,
    PromptEvaluationResponse,
    PromptStatusRequest,
    PromptListResponse,
    PromptImagesResponse,
    PromptMetaUpdateRequest,
    PromptResponse,
    PromptVersionCreateRequest,
    PromptVersionResponse,
    PreviewImageRequest,
    prompt_response,
    prompt_evaluation_response,
    prompt_version_response,
)
from app.services import prompt_image_service, prompt_scoring_service, prompt_service
from app.services.prompt_composer import compose_structured

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.post("/compose", response_model=ComposeResponse, summary="结构化 Prompt 合成预览（与保存规则一致）")
def compose_prompt(request: ComposeRequest) -> ComposeResponse:
    if request.mode == "structured":
        composed = compose_structured(request.structured.model_dump())
    else:
        composed = request.positive_prompt
    return ComposeResponse(composed_prompt=composed)


@router.get("", response_model=PromptListResponse, response_model_exclude_unset=True, summary="Prompt 列表")
def list_prompts(
    search: str | None = Query(default=None),
    favorite: bool | None = Query(default=None),
    archived: bool | None = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_images: bool = Query(default=False),
    images_limit: int = Query(default=3, ge=1, le=10),
    include_evaluation: bool = Query(default=False),
    sort: Literal["updated_desc", "score_desc", "score_asc"] = Query(default="updated_desc"),
    status: Literal["keep", "candidate", "eliminated"] | None = Query(default=None),
    session: Session = Depends(get_session),
) -> PromptListResponse:
    # 列表选项显式透传到 service（禁止用 Session.info 之类隐式状态桥）。
    return prompt_image_service.list_prompts(
        session, search=search, favorite=favorite, archived=archived, limit=limit, offset=offset,
        include_images=include_images, images_limit=images_limit,
        include_evaluation=include_evaluation, sort=sort, status=status,
    )


@router.post("/{prompt_id}/evaluations", response_model=PromptEvaluationResponse, status_code=201,
             summary="创建人工评分")
def create_prompt_evaluation(
    prompt_id: str, request: PromptEvaluationCreateRequest, session: Session = Depends(get_session),
) -> PromptEvaluationResponse:
    return prompt_evaluation_response(prompt_scoring_service.create_evaluation(session, prompt_id, request))


@router.get("/{prompt_id}/evaluations", response_model=list[PromptEvaluationResponse], summary="人工评分历史")
def list_prompt_evaluations(
    prompt_id: str, session: Session = Depends(get_session),
) -> list[PromptEvaluationResponse]:
    return [prompt_evaluation_response(item) for item in prompt_scoring_service.list_evaluations(session, prompt_id)]


@router.post("/{prompt_id}/status", response_model=PromptResponse, summary="手动设置提示词状态")
def set_prompt_status(
    prompt_id: str, request: PromptStatusRequest, session: Session = Depends(get_session),
) -> PromptResponse:
    prompt = prompt_scoring_service.set_status(session, prompt_id, request)
    return prompt_response(prompt, prompt_service.get_current_version(session, prompt))


@router.get("/{prompt_id}/images", response_model=PromptImagesResponse, summary="Prompt 生成图片")
def list_prompt_images(
    prompt_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    version_id: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> PromptImagesResponse:
    return prompt_image_service.list_prompt_images(
        session, prompt_id, limit=limit, offset=offset, version_id=version_id,
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


@router.put("/{prompt_id}/preview-image", response_model=PromptResponse, summary="设置 / 更换封面预览图（元数据，不产生版本）")
def set_prompt_preview_image(
    prompt_id: str, request: PreviewImageRequest, session: Session = Depends(get_session)
) -> PromptResponse:
    prompt = prompt_service.set_preview_image(session, prompt_id, request.image_id)
    return prompt_response(prompt, prompt_service.get_current_version(session, prompt))


@router.delete("/{prompt_id}/preview-image", response_model=PromptResponse, summary="清除封面预览图（元数据，不产生版本）")
def clear_prompt_preview_image(prompt_id: str, session: Session = Depends(get_session)) -> PromptResponse:
    prompt = prompt_service.clear_preview_image(session, prompt_id)
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
