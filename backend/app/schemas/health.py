"""健康检查响应结构（Phase 0 规范 §十五）。

2026-11-16：为 ControlHub 接入补产品身份字段（onboarding 要求就绪接口能证明
“我是谁”，而不是只回一个通用 200 / status=ok）。字段为附加字段，旧调用方
只读 status/version 不受影响。
"""
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str
    # 产品身份（ControlHub readiness identity）
    product: str = "nsfw-studio-v2"
    instance_mode: str = "scheduled_task"
    lifecycle_target: str = "\\AIHome\\NSFWStudioV2"
