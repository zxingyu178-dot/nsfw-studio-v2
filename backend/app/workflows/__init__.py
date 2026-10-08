"""工作流模块层：标准契约 + WorkflowModule 接口规范 + 注册表 / 执行入口。"""
from app.workflows.base import (
    InputImageRef,
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
from app.workflows.upscale import UpscaleModule

__all__ = [
    "BasicGenerateModule",
    "InputImageRef",
    "JobRequestContext",
    "ModuleCapabilities",
    "ModuleRegistry",
    "ParameterSpec",
    "PipelineExecutor",
    "UpscaleModule",
    "WorkflowInput",
    "WorkflowModule",
    "WorkflowOutput",
    "WorkflowValidation",
    "default_registry",
]
