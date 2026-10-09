"""结构化 Prompt 与 Workbench 快照的共享契约（Phase 1 规范 §八、§五十二）。

前端与后端使用同一套字段名（八部分顺序永久固定），
由本文件 + frontend/src/types/workbench.ts 双侧镜像，字段名不得各自另起。
"""
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.prompt_composer import loads_structured

PromptMode = Literal["structured", "full"]
# Phase 6 Task7：生成模式（文生图 / 图片生成）——显式字段，禁止长期靠"有没有 input_images"反推
GenerationMode = Literal["text", "image"]


class StructuredPromptModel(BaseModel):
    """结构化 Prompt 八部分（顺序永久固定）。"""

    style: str = ""
    face: str = ""
    clothing: str = ""
    pose: str = ""
    scene: str = ""
    composition: str = ""
    lighting: str = ""
    extra: str = ""


class SelectedAssetRef(BaseModel):
    """工作台引用的素材版本（快照关系在 Recipe 端再固化）。"""

    asset_id: str
    asset_version_id: str
    name: str = ""


class InputImageRefModel(BaseModel):
    """工作台输入图片（Phase 5 §八：统一使用 image_id，禁止保存临时外部路径）。

    第一版只支持一张（role=source，max_length=1）；未来 Reference 多图再扩展 Slots。
    """

    role: Literal["source"] = "source"
    image_id: str


class GenerationSettingsModel(BaseModel):
    """生成基础配置（model_ref 仅为未来模型引用槽位，禁止绑定具体模型）。"""

    model_ref: str | None = None
    width: int = 1024
    height: int = 1024
    seed_mode: str = "random"
    # Phase 6 Task7：Recipe / Job 快照往返携带生成模式（旧数据无该字段 → None，前端按输入图推断）
    generation_mode: GenerationMode | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowModuleRefModel(BaseModel):
    """正式工作流模块引用（Phase 5.1 Task1）：执行身份 + 模块配置的唯一核心契约。

    禁止再把无约束 ``dict[str, Any]`` 当作核心工作流契约；字段与
    ``frontend/src/types/workbench.ts`` 的 WorkflowModuleRef 双侧镜像。

    - 普通新建工作台只携带 module_id（+ 可选 config），由后端解析当前默认身份；
    - 从历史 Job / 配方 / 图片恢复时携带完整身份（含双指纹），提交时固定原版本精确重现；
    - config：模块参数（如 img2img 的 denoise），经
      Workbench → Recipe → Job.workflow_snapshot → JobStage.config_json 单链传递。
    """

    module_id: str = Field(min_length=1, max_length=64)
    module_version: str | None = None
    provider: str | None = None
    binding_version: str | None = None
    workflow_hash: str | None = None
    binding_hash: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowSnapshotModel(BaseModel):
    """工作流快照（执行真源）：模块执行身份列表（Phase 5.1 Task1 正式类型化）。"""

    modules: list[WorkflowModuleRefModel] = Field(default_factory=list)


class WorkbenchSnapshotModel(BaseModel):
    """统一工作台快照：Prompt / Asset / Recipe（未来 Image / Agent）→ 生成工作台共用。

    数值范围是通用安全边界（Phase 2.1 §八：不能只依赖前端 clamp）；
    更具体的模型能力限制由 WorkflowModule / provider binding 校验。
    Prompt 长度上限在 JobService 侧统一校验（避免影响既有读路径）。
    """

    prompt_mode: PromptMode = "structured"
    structured_prompt: StructuredPromptModel = Field(default_factory=StructuredPromptModel)
    full_prompt: str = ""
    negative_prompt: str = ""
    selected_assets: dict[str, SelectedAssetRef] = Field(default_factory=dict)
    # Phase 5：输入图片（image_id 统一引用图库；第一版 max=1，role=source）
    input_images: list[InputImageRefModel] = Field(default_factory=list, max_length=1)
    # Phase 6 Task7：生成模式显式字段（向后兼容：None = 旧快照，按 input_images / Primary Module 推断）。
    # 图片生成（含未来 Reference）不会因为"暂时没有选择图片"被自动改回文生图。
    generation_mode: GenerationMode | None = None
    width: int = Field(default=1024, ge=64, le=4096)
    height: int = Field(default=1024, ge=64, le=4096)
    count: int = Field(default=1, ge=1, le=64)
    seed_mode: str = "random"
    seed: int | None = Field(default=None, ge=0, le=2147483647)  # "使用此图 Seed"（§四十七）；None=随机
    # Phase 5.1 Task1：工作流模块正式契约（module_id + 可选执行身份 + 模块 config）
    workflow_modules: list[WorkflowModuleRefModel] = Field(default_factory=list)
    source_prompt_id: str | None = None
    source_prompt_version_id: str | None = None


def structured_model_from_json(raw: str | None) -> StructuredPromptModel:
    data = loads_structured(raw)
    return StructuredPromptModel(**data)
