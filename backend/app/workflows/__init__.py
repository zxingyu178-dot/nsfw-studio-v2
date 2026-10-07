"""工作流模块层：标准契约 + WorkflowModule 接口规范 + 注册表 / 执行入口。"""
from app.workflows.base import (
    JobRequestContext,
    ModuleCapabilities,
    ParameterSpec,
    WorkflowInput,
    WorkflowModule,
    WorkflowOutput,
    WorkflowValidation,
)
from app.workflows.basic_generate import BasicGenerateModule
from app.workflows.pipeline import PipelineExecutor
from app.workflows.registry import ModuleRegistry, default_registry

__all__ = [
    "BasicGenerateModule",
    "JobRequestContext",
    "ModuleCapabilities",
    "ModuleRegistry",
    "ParameterSpec",
    "PipelineExecutor",
    "WorkflowInput",
    "WorkflowModule",
    "WorkflowOutput",
    "WorkflowValidation",
    "default_registry",
]
