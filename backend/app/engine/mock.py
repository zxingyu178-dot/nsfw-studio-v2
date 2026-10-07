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


# 测试 fixture：最小合法 PNG（1×1 透明像素）。
# Mock 的"生成结果"只能是固定 fixture（规范 §二十二），Image.source 会标记为 mock，
# 绝不冒充真实引擎产物。
PNG_FIXTURE = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000d49444154789c6260000000060005"
    "27de3bbb0000000049454e44ae426082"
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
        # 输出故障模拟（Phase 2.1 §一）：no_outputs=成功但无输出；
        # outputs_error=取输出时抛指定错误类型
        self.no_outputs: bool = bool(options.get("no_outputs", False))
        self.outputs_error: str | None = options.get("outputs_error")
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
        if self.mode == "offline" or not self.online:
            # 掉线必须显式失败，不得静默返回 running（Phase 2.1 §二）
            raise EngineError("ENGINE_OFFLINE", "mock engine is offline")
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
        """返回测试 fixture PNG（§一 起 COMPLETED 必须有可导入输出；source=mock 标识来源）。"""
        if self.outputs_error:
            raise EngineError(self.outputs_error, f"mock 输出故障: {self.outputs_error}")
        if self.no_outputs:
            return []
        return [EngineOutputFile(filename=f"{engine_job_id}.png", data=PNG_FIXTURE)]

    async def cancel_job(self, engine_job_id: str) -> bool:
        self._canceled.add(engine_job_id)
        return True

    # ===== 测试辅助 =====
    def set_offline(self, offline: bool) -> None:
        self.online = not offline
