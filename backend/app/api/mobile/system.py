"""Mobile Bridge 系统端点（仅开放 health）。

GET /mobile/system/health —— 开放，无需 Bearer。
返回固定能力集，**绝不**包含 permanent_delete / engine_control / generation /
prompt_edit（这些只存在于 Desktop 8000）。
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.mobile_version import MOBILE_API_CONTRACT, MOBILE_BRIDGE_VERSION, build_identity

router = APIRouter(prefix="/mobile/system", tags=["mobile-system"])

CAPABILITIES = [
    "image_review",
    "review_session",
    "favorite",
    "thumbnail",
    "preview",
    "original",
    # W3.0 事件/快照能力
    "image_event_feed",
    "image_detail",
    "prompt_version_evaluation",
    "idempotent_mutation",
    "snapshot_resync",
    # W3.1 MediaReview V2 客户端冻结能力
    "mobile_feed_v2",
    "mobile_gallery_query_v1",
    "mobile_gallery_bidirectional_v1",
    "mobile_gallery_filters_v1",
    "mobile_gallery_review_filter_v1",
    "mobile_gallery_search_v1",
    # 图库按底模筛选：GET /mobile/images/gallery?model= + GET /mobile/images/models
    "mobile_gallery_model_filter_v1",
    "mobile_image_batch_review_v1",
    "mobile_image_details_v2",
    "mobile_image_decision_v2",
    "mobile_prompt_review_v2",
    "mobile_prompt_evaluation_v2",
    # 只读生图进度（不提供生成控制）
    "mobile_generation_progress_v1",
    # 进度快照新增只读队列状态：active_status / queued_jobs / paused_jobs
    "mobile_generation_queue_status_v1",
    # 进度快照新增当前张完成度：current_progress（0..1，只读）
    "mobile_generation_item_progress_v1",
    # 进度快照新增运行中任务底模：model（只读；排队/旧任务为 null）
    "mobile_generation_model_v1",
]


@router.get("/health", summary="Bridge 健康（开放）")
def health(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "product": "nsfw-studio",
        "version": MOBILE_BRIDGE_VERSION,
        "api_contract": MOBILE_API_CONTRACT,
        "capabilities": list(CAPABILITIES),
        **build_identity(CAPABILITIES),
    }
