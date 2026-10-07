"""结构化 Prompt 与 Workbench 快照的共享契约（Phase 1 规范 §八、§五十二）。

前端与后端使用同一套字段名（八部分顺序永久固定），
由本文件 + frontend/src/types/workbench.ts 双侧镜像，字段名不得各自另起。
"""
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.prompt_composer import loads_structured

PromptMode = Literal["structured", "full"]


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


class GenerationSettingsModel(BaseModel):
    """生成基础配置（model_ref 仅为未来模型引用槽位，禁止绑定具体模型）。"""

    model_ref: str | None = None
    width: int = 1024
    height: int = 1024
    seed_mode: str = "random"
    params: dict[str, Any] = Field(default_factory=dict)


class WorkflowSnapshotModel(BaseModel):
    """工作流快照：Phase 1 为空列表，结构预留 module_id / module_version / config。"""

    modules: list[dict[str, Any]] = Field(default_factory=list)


class WorkbenchSnapshotModel(BaseModel):
    """统一工作台快照：Prompt / Asset / Recipe（未来 Image / Agent）→ 生成工作台共用。"""

    prompt_mode: PromptMode = "structured"
    structured_prompt: StructuredPromptModel = Field(default_factory=StructuredPromptModel)
    full_prompt: str = ""
    negative_prompt: str = ""
    selected_assets: dict[str, SelectedAssetRef] = Field(default_factory=dict)
    width: int = 1024
    height: int = 1024
    count: int = 1
    seed_mode: str = "random"
    seed: int | None = None  # "使用此图 Seed"（规范 §四十七）；None=随机
    workflow_modules: list[dict[str, Any]] = Field(default_factory=list)
    source_prompt_id: str | None = None
    source_prompt_version_id: str | None = None


def structured_model_from_json(raw: str | None) -> StructuredPromptModel:
    data = loads_structured(raw)
    return StructuredPromptModel(**data)
