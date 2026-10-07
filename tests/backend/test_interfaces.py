"""接口预留存在性检查（Phase 0 规范 §十三、§十四：只定义规范，不绑定引擎）。"""
from __future__ import annotations

import inspect


def test_workflow_module_interface_exists():
    from app.workflows import WorkflowModule

    assert inspect.isabstract(WorkflowModule)
    for method in ("validate_input", "execute", "get_output"):
        assert method in dir(WorkflowModule)


def test_engine_adapter_interface_exists():
    from app.engine import EngineAdapter

    assert inspect.isabstract(EngineAdapter)
    for method in ("health", "submit_job", "get_job_status", "cancel_job"):
        assert method in dir(EngineAdapter)


def test_queue_worker_interface_exists():
    from app.workers import QueueWorker

    assert inspect.isabstract(QueueWorker)


def test_no_engine_binding_in_configs():
    """workflow.yaml 不得绑定具体引擎（Phase 0 规范 §一）。"""
    from app.core.config import load_settings

    raw = load_settings().workflow.raw
    provider = (raw.get("engine") or {}).get("provider", "unbound")
    assert provider == "unbound"
