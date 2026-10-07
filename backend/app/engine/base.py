"""EngineAdapter 接口规范（Phase 0 规范 §十四）。

Phase 0 不绑定任何生成引擎：不写引擎地址、节点 ID、模型名或 Workflow JSON。
未来 ``ComfyUIAdapter`` 等具体实现放在 ``engine/adapters/``，通过 configs 选择，
新增引擎适配器不得修改核心代码。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class EngineStatus:
    online: bool
    detail: str = ""


class EngineAdapter(ABC):
    """生成引擎适配器接口。

    Phase 0 仅定义规范，不做任何实现。上层（workers / services）
    只依赖本接口，不感知具体引擎。
    """

    name: str = "base"
    version: str = "0.0.0"

    @abstractmethod
    async def health(self) -> EngineStatus:
        """探测引擎是否可用。"""

    @abstractmethod
    async def submit_job(self, request: dict[str, Any]) -> str:
        """提交生成任务，返回 engine_job_id。"""

    @abstractmethod
    async def get_job_status(self, engine_job_id: str) -> dict[str, Any]:
        """查询引擎侧任务状态。"""

    @abstractmethod
    async def cancel_job(self, engine_job_id: str) -> bool:
        """取消引擎侧任务，返回是否成功。"""
