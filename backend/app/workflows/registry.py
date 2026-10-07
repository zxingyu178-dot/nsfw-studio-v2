"""ModuleRegistry — WorkflowModule 注册表（Phase 2.1 规范 §三）。

按 (module_id, module_version) 注册；PipelineExecutor 据此从 Job 的
workflow_snapshot 解析实际执行的模块。新增 Upscale / Img2Img / Reference 模块时
只需注册新模块，不修改 Worker 核心执行逻辑。
"""
from __future__ import annotations

from collections.abc import Iterable

from app.engine.base import EngineError
from app.workflows.base import WorkflowModule
from app.workflows.basic_generate import BasicGenerateModule


class ModuleRegistry:
    def __init__(self, modules: Iterable[WorkflowModule] | None = None) -> None:
        self._by_key: dict[tuple[str, str], WorkflowModule] = {}
        for module in modules or ():
            self.register(module)

    def register(self, module: WorkflowModule) -> None:
        self._by_key[(module.module_id, module.module_version)] = module

    def get(self, module_id: str, module_version: str | None = None) -> WorkflowModule:
        """按 id（+可选版本）取模块；未注册时抛 WORKFLOW_ERROR（Job 侧可控失败）。"""
        if module_version is not None:
            found = self._by_key.get((module_id, module_version))
            if found is not None:
                return found
        candidates = [module for (mid, _version), module in self._by_key.items() if mid == module_id]
        if not candidates:
            raise EngineError("WORKFLOW_ERROR", f"WorkflowModule 未注册: {module_id}")
        if module_version is not None:
            raise EngineError(
                "WORKFLOW_ERROR", f"WorkflowModule 版本不存在: {module_id}@{module_version}"
            )
        return candidates[0]

    def has(self, module_id: str, module_version: str | None = None) -> bool:
        try:
            self.get(module_id, module_version)
            return True
        except EngineError:
            return False

    def ids(self) -> list[str]:
        return sorted({mid for mid, _version in self._by_key})


def default_registry() -> ModuleRegistry:
    """产品默认注册表：当前含基础生图模块（Phase 2.1 只此一个）。"""
    return ModuleRegistry([BasicGenerateModule()])