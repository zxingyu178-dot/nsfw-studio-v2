"""未接入引擎时的占位适配器：health 返回离线，其余操作直接拒绝。"""
from __future__ import annotations

from app.engine.base import (
    EngineAdapter,
    EngineError,
    EngineJobRequest,
    EngineJobStatus,
    EngineOutputFile,
    EngineStatus,
)


class UnboundEngineAdapter(EngineAdapter):
    name = "unbound"
    version = "0.0.0"

    async def health(self) -> EngineStatus:
        return EngineStatus(online=False, detail="尚未接入生成引擎", engine_name=self.name)

    async def submit_job(self, request: EngineJobRequest) -> str:
        raise EngineError("ENGINE_OFFLINE", "尚未接入生成引擎")

    async def get_job_status(self, engine_job_id: str) -> EngineJobStatus:
        return EngineJobStatus(state="unknown", message="尚未接入生成引擎")

    async def get_job_outputs(self, engine_job_id: str) -> list[EngineOutputFile]:
        return []

    async def cancel_job(self, engine_job_id: str) -> bool:
        return False
