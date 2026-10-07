"""接口契约检查（Phase 0.1 收口）。

- WorkflowModule 标准契约类型存在（禁止无约束 dict 作为模块间唯一契约）；
- EngineAdapter 类型化契约存在；
- QueueWorker 不承担 Job 创建职责（只消费已存在的 Job）。
"""
from __future__ import annotations

import dataclasses
import inspect


def test_workflow_standard_contracts_exist():
    from app.workflows import (
        ModuleCapabilities,
        ParameterSpec,
        WorkflowInput,
        WorkflowModule,
        WorkflowOutput,
        WorkflowValidation,
    )

    for contract in (ModuleCapabilities, ParameterSpec, WorkflowInput, WorkflowOutput, WorkflowValidation):
        assert dataclasses.is_dataclass(contract), contract
    assert inspect.isabstract(WorkflowModule)
    for method in ("capabilities", "validate_input", "execute"):
        assert method in dir(WorkflowModule)
    # execute 必须接收 EngineAdapter（引擎调用只发生在 EngineAdapter）
    execute_params = inspect.signature(WorkflowModule.execute).parameters
    assert "engine" in execute_params


def test_workflow_module_rejects_unconstrained_result():
    """execute 的返回契约必须是 WorkflowOutput，而不是无约束 dict。"""
    from app.workflows import WorkflowModule
    from app.workflows.base import WorkflowOutput

    annotations = inspect.signature(WorkflowModule.execute).return_annotation
    assert "WorkflowOutput" in str(annotations)


def test_engine_adapter_contract_exists():
    from app.engine import EngineAdapter, EngineJobRequest, EngineJobStatus, EngineStatus

    assert dataclasses.is_dataclass(EngineStatus)
    assert dataclasses.is_dataclass(EngineJobRequest)
    assert dataclasses.is_dataclass(EngineJobStatus)
    assert "progress" in getattr(EngineJobStatus, "__dataclass_fields__"), "必须声明进度能力"
    assert inspect.isabstract(EngineAdapter)
    for method in ("health", "submit_job", "get_job_status", "cancel_job"):
        assert method in dir(EngineAdapter)


def test_queue_worker_does_not_create_jobs():
    """Worker 只消费已存在的 Job：接口不得有 submit/创建类入口。"""
    from app.workers import QueueWorker, WorkerStatus

    assert inspect.isabstract(QueueWorker)
    assert not hasattr(QueueWorker, "submit"), "Worker 不得承担 Job 创建职责"
    for method in ("start", "stop", "status", "process_job"):
        assert method in dir(QueueWorker)
    assert dataclasses.is_dataclass(WorkerStatus)


def test_no_engine_binding_in_configs():
    """workflow.yaml 不得绑定具体引擎（规范 §一）。"""
    from app.core.config import load_settings

    raw = load_settings().workflow.raw
    provider = (raw.get("engine") or {}).get("provider", "unbound")
    assert provider == "unbound"
