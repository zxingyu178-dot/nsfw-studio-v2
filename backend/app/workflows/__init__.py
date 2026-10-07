"""工作流模块层：标准契约 + WorkflowModule 接口规范。"""
from app.workflows.base import (
    ModuleCapabilities,
    ParameterSpec,
    WorkflowInput,
    WorkflowModule,
    WorkflowOutput,
    WorkflowValidation,
)

__all__ = [
    "ModuleCapabilities",
    "ParameterSpec",
    "WorkflowInput",
    "WorkflowModule",
    "WorkflowOutput",
    "WorkflowValidation",
]
