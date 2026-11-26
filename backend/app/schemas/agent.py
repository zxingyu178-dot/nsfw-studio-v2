"""Agent / AI 提交契约（Phase 0.34；W1.2）。

只允许单次文生图（无输入图片的生成型模块）；复杂链请用 UI。
module_id 可选：不传/null 时使用服务端当前配置的默认工作流（不在请求里写死默认）。
安全边界：Bearer token（config.local `agent.token` 或环境变量）+ 每分钟限速；
8000 仍固定 loopback，不对公网暴露。
# 注意：`upscale` 参数已随产品下线；出现该字段时由端点显式 422（AGENT_UPSCALE_REMOVED）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentLoraSpec(BaseModel):
    """单条任务级 LoRA；名称必须是 ComfyUI /models/loras 中的文件名。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    strength_model: float = Field(default=1.0, ge=-2.0, le=2.0)
    strength_clip: float = Field(default=1.0, ge=-2.0, le=2.0)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("LoRA 文件名不能为空")
        if "/" in name or "\\" in name:
            raise ValueError("LoRA 文件名不得包含路径")
        return name


class AgentSamplingParams(BaseModel):
    """任务级采样参数；不传的字段沿用 binding 默认值。"""

    model_config = ConfigDict(extra="forbid")

    steps: int | None = Field(default=None, ge=1, le=100)
    cfg: float | None = Field(default=None, ge=1.0, le=20.0)
    sampler_name: str | None = Field(default=None, max_length=64)
    scheduler: str | None = Field(default=None, max_length=64)
    denoise: float | None = Field(default=None, ge=0.0, le=1.0)
    face_detailer: bool | None = Field(
        default=None,
        description="人脸修复（FaceDetailer）；False 可显著提速，不传=binding 默认（开启）",
    )


class AgentJobRequest(BaseModel):
    """AI 助手（豆包/本地 Agent）提交一次生成请求。"""

    # 保留未知字段以便显式识别已下线参数（如 upscale），绝不静默忽略。
    model_config = ConfigDict(extra="allow")

    prompt: str = Field(min_length=1, max_length=10000, description="正向 Prompt（最终文本）")
    negative_prompt: str = Field(default="", max_length=8000, description="负向 Prompt")
    module_id: str | None = Field(
        default=None,
        max_length=64,
        description="工作流模块；不传=服务器当前默认。可用性由服务端校验，禁止客户端枚举",
    )
    module_version: str | None = Field(
        default=None,
        max_length=32,
        description="模块代码版本；不传=服务器默认。显式传入时与服务端注册表校验",
    )
    binding_version: str | None = Field(
        default=None,
        max_length=32,
        description="Provider binding 版本；不传=服务器默认。例如 anime_generate 的 v15",
    )
    model: str | None = Field(
        default=None,
        max_length=255,
        description="ComfyUI /models/checkpoints 中的底模文件名；不传=绑定默认",
    )
    loras: list[AgentLoraSpec] = Field(
        default_factory=list,
        max_length=2,
        description="任务级 LoRA，最多 2 条",
    )
    params: AgentSamplingParams | None = Field(
        default=None,
        description="采样参数覆盖：steps/cfg/sampler_name/scheduler/denoise",
    )
    use_recommended_sampling: bool = Field(
        default=False,
        description=(
            "自动套用模型注册中心的推荐采样参数；省略 model 时使用 binding 默认底模，"
            "显式 params 优先，未登记推荐的底模返回 422"
        ),
    )
    width: int = Field(default=1024, ge=64, le=4096)
    height: int = Field(default=1024, ge=64, le=4096)
    count: int = Field(default=1, ge=1, le=64)
    seed: int | None = Field(default=None, ge=0, le=2147483647, description="固定 Seed；不传=随机")
    queue_mode: Literal["normal", "next"] = Field(default="normal", description="next=插队到当前任务之后")
    client_request_id: str | None = Field(
        default=None, max_length=128,
        description="幂等键：同一键重复提交返回原 Job（不重复生成）",
    )

    @field_validator("module_id")
    @classmethod
    def _validate_module_id(cls, value: str | None) -> str | None:
        """W1.2.1：严格区分 None 与空字符串——只有真正未传入才允许走默认。"""
        if value is None:
            return None
        if not value.strip():
            raise ValueError("module_id 不能为空字符串或纯空白")
        return value.strip()

    @field_validator("module_version", "binding_version")
    @classmethod
    def _validate_version(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("版本号不能为空字符串或纯空白")
        return normalized

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        model = value.strip()
        if not model:
            raise ValueError("model 不能为空字符串或纯空白")
        if "/" in model or "\\" in model:
            raise ValueError("model 不得包含路径，只填 ComfyUI /models/checkpoints 中的文件名")
        return model
