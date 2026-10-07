"""EngineAdapter 工厂：按 configs 选择引擎实现（不修改核心）。"""
from __future__ import annotations

from app.core.config import Settings
from app.engine.base import EngineAdapter


def create_engine_adapter(settings: Settings) -> EngineAdapter:
    engine_cfg = (settings.workflow.raw or {}).get("engine") or {}
    provider = engine_cfg.get("provider", "unbound")
    options = engine_cfg.get("options") or {}

    if provider == "mock":
        from app.engine.mock import MockEngineAdapter

        return MockEngineAdapter(options)
    if provider == "comfyui":
        from app.engine.comfyui import ComfyUIAdapter

        return ComfyUIAdapter(
            options,
            comfyui_config=settings.comfyui,
            module_id=str(engine_cfg.get("module_id", "basic_generate")),
            binding_version=str(engine_cfg.get("binding_version", "v1")),
        )
    from app.engine.unbound import UnboundEngineAdapter

    return UnboundEngineAdapter()


def module_identity(settings: Settings) -> dict[str, str | None]:
    """当前引擎/模块身份（规范 §五十五：Job 必须记录实际使用的版本）。

    comfyui 时从 provider binding 读取真实 binding_version 与 workflow_hash，
    确保以后 Workflow 被修改仍能追溯老 Job 当时使用的版本。
    """
    engine_cfg = (settings.workflow.raw or {}).get("engine") or {}
    provider = engine_cfg.get("provider", "unbound")
    identity: dict[str, str | None] = {
        "module_id": engine_cfg.get("module_id", "basic_generate"),
        "module_version": engine_cfg.get("module_version", "v1"),
        "provider": provider,
        "binding_version": engine_cfg.get("binding_version", "v1"),
        "workflow_hash": None,
    }
    if provider == "comfyui":
        from app.engine.comfyui import ComfyUIAdapter

        adapter = ComfyUIAdapter(
            engine_cfg.get("options") or {},
            comfyui_config=settings.comfyui,
            module_id=str(engine_cfg.get("module_id", "basic_generate")),
            binding_version=str(engine_cfg.get("binding_version", "v1")),
        )
        identity["binding_version"] = adapter.binding_version
        identity["workflow_hash"] = adapter.workflow_hash
    return identity
