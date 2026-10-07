"""引擎错误分类（Phase 2 规范 §三十五、§三十六）。

分类决定重试策略：
- ENGINE_NETWORK（瞬态）→ 自动重试，最多 2 次；
- ENGINE_OFFLINE / OUT_OF_MEMORY / WORKFLOW_ERROR / MODEL_MISSING / NODE_MISSING →
  系统性失败：当前 Job FAILED + 队列自动暂停，不重试；
- OUTPUT_MISSING / STORAGE_ERROR / UNKNOWN_ENGINE_ERROR → 不重试。
"""
from __future__ import annotations

import re

ERROR_TYPES = (
    "ENGINE_OFFLINE",
    "ENGINE_NETWORK",
    "WORKFLOW_ERROR",
    "MODEL_MISSING",
    "NODE_MISSING",
    "OUT_OF_MEMORY",
    "OUTPUT_MISSING",
    "STORAGE_ERROR",
    "UNKNOWN_ENGINE_ERROR",
)

_SYSTEMIC_TYPES = {
    "ENGINE_OFFLINE",
    "OUT_OF_MEMORY",
    "WORKFLOW_ERROR",
    "MODEL_MISSING",
    "NODE_MISSING",
}

_MODEL_HINTS = re.compile(r"checkpoint|model.*(not|missing|failed to load)|weights", re.IGNORECASE)
_NODE_HINTS = re.compile(r"node.*(not found|missing)|custom node|unknown node", re.IGNORECASE)
_OOM_HINTS = re.compile(r"out of memory|cuda oom|not enough memory", re.IGNORECASE)
_WORKFLOW_HINTS = re.compile(r"prompt.*error|workflow|validation|failed to validate", re.IGNORECASE)


def classify_engine_message(message: str) -> str:
    """把引擎错误文本映射到标准错误类型。"""
    if not message:
        return "UNKNOWN_ENGINE_ERROR"
    if _OOM_HINTS.search(message):
        return "OUT_OF_MEMORY"
    if _MODEL_HINTS.search(message):
        return "MODEL_MISSING"
    if _NODE_HINTS.search(message):
        return "NODE_MISSING"
    if _WORKFLOW_HINTS.search(message):
        return "WORKFLOW_ERROR"
    return "UNKNOWN_ENGINE_ERROR"


def is_systemic(error_type: str) -> bool:
    """系统性失败（规范 §二十一）：Job FAILED + 队列自动暂停，不继续烧完队列。"""
    return error_type in _SYSTEMIC_TYPES
