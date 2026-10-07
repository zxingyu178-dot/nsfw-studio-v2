"""WorkflowModule 接口规范（Phase 0 规范 §十三）。

只定义规范，不做实现，不绑定 ComfyUI。
未来的高清 / 图生图 / 参考图 / AI Agent 等能力都以 WorkflowModule 形式扩展，
新增扩展模块不得修改核心代码。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowValidation:
    ok: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class WorkflowResult:
    workflow: str
    outputs: dict[str, Any] = field(default_factory=dict)


class WorkflowModule(ABC):
    """生成工作流模块接口。

    每个模块声明 ``name`` / ``version``；输入输出用 dict 传递，
    具体结构由各模块在 ``validate_input`` 中校验。
    """

    name: str = "base"
    version: str = "0.0.0"

    @abstractmethod
    def validate_input(self, payload: dict[str, Any]) -> WorkflowValidation:
        """校验输入；不合法时返回 ok=False 与错误列表。"""

    @abstractmethod
    def execute(self, payload: dict[str, Any]) -> WorkflowResult:
        """执行工作流（Phase 1+ 由具体模块实现）。"""

    @abstractmethod
    def get_output(self, result: WorkflowResult) -> dict[str, Any]:
        """从执行结果中提取标准输出（如图片引用、元数据）。"""
