"""PipelineExecutor — QueueWorker 与 WorkflowModule 之间的唯一执行入口（Phase 2.1 §三）。

```
QueueWorker
  ↓ 根据 Job Workflow Snapshot 解析模块
PipelineExecutor.resolve_module(job)
  ↓ BasicGenerateModule（标准输入 / 引擎请求由模块构造）
WorkflowModule.build_engine_request(context)
  ↓
EngineAdapter → provider binding
```

QueueWorker 不包含任何模块专属参数名（basic_generate 的参数结构只在模块内）。
"""
from __future__ import annotations

import json
from typing import Any

from app.engine.base import EngineAdapter, EngineError, EngineJobRequest
from app.models import Job, JobItem
from app.workflows.base import JobRequestContext, WorkflowInput, WorkflowModule, WorkflowOutput
from app.workflows.registry import ModuleRegistry, default_registry


class PipelineExecutor:
    def __init__(self, registry: ModuleRegistry | None = None) -> None:
        self._registry = registry or default_registry()

    @property
    def registry(self) -> ModuleRegistry:
        return self._registry

    # ===== 模块解析 =====
    def resolve_module(self, job: Job) -> WorkflowModule:
        """从 Job 的 workflow_snapshot.modules[0] 解析实际执行的模块（§四）。"""
        snapshot: dict[str, Any] = {}
        if job.workflow_snapshot_json:
            try:
                snapshot = json.loads(job.workflow_snapshot_json)
            except ValueError:
                snapshot = {}
        modules = snapshot.get("modules") or []
        module_id: str | None = None
        module_version: str | None = None
        if modules and isinstance(modules[0], dict):
            module_id = modules[0].get("module_id")
            module_version = modules[0].get("module_version")
        module_id = module_id or job.module_id
        module_version = module_version or job.module_version
        if not module_id:
            raise EngineError("WORKFLOW_ERROR", "Job 缺少 Workflow 模块快照")
        return self._registry.get(module_id, module_version)

    def build_context(self, job: Job, seed: int, *, item: JobItem | None = None,
                      metadata: dict[str, Any] | None = None) -> JobRequestContext:
        return JobRequestContext(
            positive_prompt=job.positive_prompt_snapshot,
            negative_prompt=job.negative_prompt_snapshot,
            generation_settings=json.loads(job.generation_settings_json or "{}"),
            seed=seed,
            metadata=metadata if metadata is not None else {
                "job_id": job.id,
                "item_id": item.id if item is not None else None,
            },
        )

    # ===== Worker 细粒度路径：只构造引擎请求（提交/轮询/取消语义留在 Worker） =====
    def build_engine_request(self, job: Job, item: JobItem, seed: int) -> EngineJobRequest:
        module = self.resolve_module(job)
        context = self.build_context(job, seed, item=item)
        return module.build_engine_request(context)

    # ===== Pipeline 直跑路径：模块完整执行（提交 → 等待 → 取回引用） =====
    async def execute(self, job: Job, seed: int, adapter: EngineAdapter) -> WorkflowOutput:
        module = self.resolve_module(job)
        payload: WorkflowInput = module.build_input(self.build_context(job, seed))
        return await module.execute(payload, adapter)