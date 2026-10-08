"""PipelineExecutor — QueueWorker 与 WorkflowModule 之间的唯一执行入口（Phase 2.1 §三；Phase 3 阶段化）。

```
QueueWorker
  ↓ 根据 JobStage（固化身份）解析模块
PipelineExecutor.resolve_stage_module(stage)
  ↓ BasicGenerateModule / UpscaleModule（标准输入 / 引擎请求由模块构造）
WorkflowModule.prepare_inputs → build_engine_request
  ↓
EngineAdapter → provider binding（每次请求动态绑定，§0.2/§二十二）
```

QueueWorker 不包含任何模块专属参数名（模块的参数结构只在模块内）。
执行身份一律来自 JobStage（module/binding/hash 固化），绝不读取当前配置（§二十三）。
"""
from __future__ import annotations

import json
from typing import Any

from app.engine.base import EngineAdapter, EngineBindingRef, EngineError, EngineJobRequest
from app.models import Job, JobItem, JobStage, JobStageItem
from app.workflows.base import (
    InputImageRef,
    JobRequestContext,
    WorkflowInput,
    WorkflowModule,
    WorkflowOutput,
)
from app.workflows.registry import ModuleRegistry, default_registry


class PipelineExecutor:
    def __init__(self, registry: ModuleRegistry | None = None) -> None:
        self._registry = registry or default_registry()

    @property
    def registry(self) -> ModuleRegistry:
        return self._registry

    # ===== 模块解析 =====
    def resolve_stage_module(self, stage: JobStage) -> WorkflowModule:
        """按 Stage 固化的 module 身份解析模块（§二十三：Stage 是执行真源）。"""
        return self._registry.get(stage.module_id, stage.module_version)

    def resolve_module(self, job: Job) -> WorkflowModule:
        """兼容入口（无 Stage 的直跑路径）：从 Job 的 workflow_snapshot.modules[0] 解析。"""
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

    # ===== Binding（§0.2：每次请求携带身份；Adapter 按 (module_id, binding_version) 加载） =====
    @staticmethod
    def binding_ref_for(stage: JobStage) -> EngineBindingRef | None:
        if stage.provider is None:
            return None
        return EngineBindingRef(
            module_id=stage.module_id,
            module_version=stage.module_version,
            provider=stage.provider or "unbound",
            binding_version=stage.binding_version or "v1",
            workflow_hash=stage.workflow_hash,
            binding_hash=stage.binding_hash,
        )

    # ===== 上下文 =====
    def build_context(
        self,
        job: Job,
        seed: int | None,
        *,
        stage: JobStage | None = None,
        stage_item: JobStageItem | JobItem | None = None,
        input_image: InputImageRef | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JobRequestContext:
        if metadata is None:
            metadata = {"job_id": job.id}
            if stage is not None:
                metadata.update({
                    "stage_id": stage.id,
                    "stage_index": stage.stage_index,
                    "module_id": stage.module_id,
                })
            if stage_item is not None:
                metadata["stage_item_id"] = stage_item.id
                item_id = getattr(stage_item, "job_item_id", None) or getattr(stage_item, "id", None)
                metadata["item_id"] = item_id
        return JobRequestContext(
            positive_prompt=job.positive_prompt_snapshot,
            negative_prompt=job.negative_prompt_snapshot,
            generation_settings=json.loads(job.generation_settings_json or "{}"),
            seed=seed,
            metadata=metadata,
            binding=self.binding_ref_for(stage) if stage is not None else None,
            input_image=input_image,
        )

    # ===== Worker 细粒度路径：只构造引擎请求（提交/轮询/取消语义留在 Worker） =====
    async def build_engine_request(
        self,
        job: Job,
        stage: JobStage,
        stage_item: JobStageItem,
        seed: int | None,
        adapter: EngineAdapter,
        *,
        input_image: InputImageRef | None = None,
    ) -> EngineJobRequest:
        module = self.resolve_stage_module(stage)
        context = self.build_context(job, seed, stage=stage, stage_item=stage_item,
                                     input_image=input_image)
        prepared = await module.prepare_inputs(context, adapter)
        return module.build_engine_request(context, prepared)

    # ===== Pipeline 直跑路径：模块完整执行（提交 → 等待 → 取回引用） =====
    async def execute(self, job: Job, seed: int | None, adapter: EngineAdapter,
                      *, stage: JobStage | None = None) -> WorkflowOutput:
        module = self.resolve_stage_module(stage) if stage is not None else self.resolve_module(job)
        context = self.build_context(job, seed, stage=stage)
        payload: WorkflowInput = module.build_input(context)
        return await module.execute(payload, adapter, binding=context.binding)