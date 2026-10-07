"""MockEngineAdapter（Phase 2 规范 §二十二）。

仅用于自动化测试与状态机/队列/暂停/取消/恢复/SSE/崩溃恢复演练：
- 可模拟：成功、延迟、失败、引擎离线、OOM、取消；
- 不产生任何真实图片，**不向正式图库导入文件**（不伪装真实生成结果）；
- 行为由 options 驱动（来自 configs workflow.engine.options 或测试注入）。
"""
from __future__ import annotations

import asyncio
import uuid

from app.engine.base import (
    EngineAdapter,
    EngineError,
    EngineJobRequest,
    EngineJobStatus,
    EngineOutputFile,
    EngineStatus,
)


class MockEngineAdapter(EngineAdapter):
    name = "mock"
    version = "0.1.0"

    def __init__(self, options: dict | None = None) -> None:
        options = options or {}
        self.mode = options.get("mode", "success")  # success|fail|offline|oom|workflow_error
        self.delay_per_item_ms: int = int(options.get("delay_per_item_ms", 50))
        self.fail_after_items: int = int(options.get("fail_after_items", 0))  # 成功 N 个 item 后开始失败
        self.offline_after_submit: bool = bool(options.get("offline_after_submit", False))
        # 瞬态网络错误模拟（规范 §三十六）：前 N 次提交抛 ENGINE_NETWORK(transient)，用于重试测试
        self.transient_fail_times: int = int(options.get("transient_fail_times", 0))
        self._transient_failures = 0
        self.supports_cancel = True
        self._canceled: set[str] = set()
        self._completed: dict[str, int] = {}
        self._submitted = 0
        self.online = True

    async def health(self) -> EngineStatus:
        if self.mode == "offline" or not self.online:
            return EngineStatus(online=False, detail="mock engine offline", engine_name=self.name)
        return EngineStatus(online=True, detail="mock engine ready", engine_name=self.name, engine_version=self.version)

    async def submit_job(self, request: EngineJobRequest) -> str:
        await asyncio.sleep(0)
        if self.mode == "offline":
            raise EngineError("ENGINE_OFFLINE", "mock engine is offline")
        if self._transient_failures < self.transient_fail_times:
            self._transient_failures += 1
            raise EngineError("ENGINE_NETWORK", "mock transient network failure", transient=True)
        self._submitted += 1
        engine_job_id = f"mock_{uuid.uuid4().hex[:12]}"
        if self.mode in ("fail", "oom", "workflow_error") or (
            self.fail_after_items and self._submitted > self.fail_after_items
        ):
            self._completed[engine_job_id] = -1  # 标记失败（具体错误由 get_job_status 报告）
        else:
            self._completed[engine_job_id] = 0
        return engine_job_id

    async def get_job_status(self, engine_job_id: str) -> EngineJobStatus:
        await asyncio.sleep(self.delay_per_item_ms / 1000)
        if engine_job_id in self._canceled:
            return EngineJobStatus(state="canceled", progress=None, stage="canceled")
        marker = self._completed.get(engine_job_id)
        if marker is None:
            return EngineJobStatus(state="unknown", progress=None, message="unknown mock job")
        if marker == -1:
            if self.mode == "oom":
                return EngineJobStatus(state="failed", progress=0.2, message="CUDA out of memory",
                                       stage="sampling")
            if self.mode == "workflow_error":
                return EngineJobStatus(state="failed", progress=0.1,
                                       message="Prompt failed to validate: node missing", stage="validation")
            return EngineJobStatus(state="failed", progress=0.3, message="mock injected failure", stage="sampling")
        # 模拟两段进度：提交 → 采样
        marker += 1
        self._completed[engine_job_id] = marker
        if marker == 1:
            return EngineJobStatus(state="running", progress=0.5, stage="sampling")
        return EngineJobStatus(state="succeeded", progress=1.0, stage="save_image")

    async def get_job_outputs(self, engine_job_id: str) -> list[EngineOutputFile]:
        """Mock 不产出图片文件（规范 §二十二：禁止把 Mock 结果伪装成真实生成图片）。"""
        return []

    async def cancel_job(self, engine_job_id: str) -> bool:
        self._canceled.add(engine_job_id)
        return True

    # ===== 测试辅助 =====
    def set_offline(self, offline: bool) -> None:
        self.online = not offline
