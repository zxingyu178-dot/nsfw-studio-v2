"""Mobile Bridge 系统端点（仅开放 health）。

GET /mobile/system/health —— 开放，无需 Bearer。
返回固定能力集，**绝不**包含 permanent_delete / engine_control / generation /
prompt_edit（这些只存在于 Desktop 8000）。
"""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/mobile/system", tags=["mobile-system"])

CAPABILITIES = [
    "image_review",
    "review_session",
    "favorite",
    "thumbnail",
    "preview",
    "original",
]


@router.get("/health", summary="Bridge 健康（开放）")
def health(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "product": "nsfw-studio",
        "version": "0.13.0",
        "api_contract": 1,
        "capabilities": list(CAPABILITIES),
    }
