"""Phase 0.12 Task11：Module Execution Timeout Policy 优先级解析测试。

_queue_worker._stage_timeout_for_ 的优先级（按序回落）：
  1) Stage 显式 override（config_json.execution_timeout，正数）
  2) 模块 capabilities().recommended_timeout_seconds（从 registry 读取，无 module_id 硬编码）
  3) 全局 fallback（默认 1800s）

本测试只断言解析逻辑，不真正起 worker 线程 / 不连引擎。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.workers.queue_worker import DEFAULT_STAGE_TIMEOUT_SECONDS, SingleQueueWorker


def _worker() -> SingleQueueWorker:
    """_stage_timeout_for 只用 self._pipeline 与 self._stage_timeout，
    session/adapter/线程循环均不触碰，可安全传 None。"""
    return SingleQueueWorker(session_factory=None, adapter=None)


def _stage(module_id: str, module_version: str = "v1", config: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        module_id=module_id,
        module_version=module_version,
        config_json=json.dumps(config) if config is not None else None,
    )


def test_reference_generate_declares_recommended_7200():
    from app.workflows.reference_generate import ReferenceGenerateModule

    assert ReferenceGenerateModule().capabilities().recommended_timeout_seconds == 7200.0


def test_reference_stage_resolves_to_module_recommended_7200():
    timeout = _worker()._stage_timeout_for(_stage("reference_generate", "v1"))
    assert timeout == 7200.0


def test_module_without_policy_falls_back_to_global_1800():
    # basic_generate 未声明 recommended_timeout_seconds → 全局 fallback
    timeout = _worker()._stage_timeout_for(_stage("basic_generate", "v1"))
    assert timeout == DEFAULT_STAGE_TIMEOUT_SECONDS == 1800.0


def test_stage_explicit_override_beats_module_recommended():
    # reference 模块推荐 7200，但 Stage 显式 override=300 → 用 300
    timeout = _worker()._stage_timeout_for(
        _stage("reference_generate", "v1", {"execution_timeout": 300})
    )
    assert timeout == 300.0


def test_stage_explicit_override_beats_global_fallback():
    # basic 模块无推荐，全局 1800；Stage 显式 override=120 → 用 120
    timeout = _worker()._stage_timeout_for(
        _stage("basic_generate", "v1", {"execution_timeout": 120})
    )
    assert timeout == 120.0


def test_invalid_override_falls_through_to_module_recommended():
    # override 存在但非法（非数字）→ 视为无效 override，回落到 module recommended=7200
    timeout = _worker()._stage_timeout_for(
        _stage("reference_generate", "v1", {"execution_timeout": "not-a-number"})
    )
    assert timeout == 7200.0


def test_custom_global_fallback_respected():
    worker = SingleQueueWorker(session_factory=None, adapter=None, stage_timeout_seconds=999.0)
    # 无 override + 无模块推荐 → 自定义全局 999
    assert worker._stage_timeout_for(_stage("basic_generate", "v1")) == 999.0
