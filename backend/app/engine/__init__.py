"""生成引擎适配器层。Phase 0/0.1 仅有接口规范，无任何具体实现。"""
from app.engine.base import EngineAdapter, EngineJobRequest, EngineJobStatus, EngineStatus

__all__ = ["EngineAdapter", "EngineJobRequest", "EngineJobStatus", "EngineStatus"]
