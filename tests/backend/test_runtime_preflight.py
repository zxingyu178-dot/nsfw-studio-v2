"""W2.0 Runtime Guard：动态检测、缓存与提交 Gate（Mock HTTP，不依赖真实 ComfyUI）。"""
from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import ENV_AGENT_TOKEN, Settings, WorkflowConfig
from app.engine.base import EngineBindingRef, EngineError, EngineStatus
from app.main import create_app
from app.models import Job, JobStage, Prompt
from app.services import runtime_preflight_service as preflight
from app.services.runtime_preflight_service import RuntimePreflightService, run_preflight

ROOT = Path(__file__).resolve().parents[2]

WORKFLOW = {
    "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "model.gguf"}},
    "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
    "4": {"class_type": "LoraLoader", "inputs": {"lora_name": "turbo.safetensors"}},
    "6": {"class_type": "KSampler", "inputs": {}},
    "7": {"class_type": "VAEDecode", "inputs": {}},
    "8": {"class_type": "SaveImage", "inputs": {}},
}
BINDING = {
    "module": "basic_generate",
    "provider": "comfyui",
    "binding_version": "v1",
    "requirements": {"comfyui_min_version": "0.37.0"},
}
MODELS = {
    "diffusion_models": ["model.gguf"],
    "text_encoders": ["clip.safetensors"],
    "vae": ["vae.safetensors"],
    "loras": ["turbo.safetensors"],
}


class FakeComfyAdapter:
    base_url = "http://fake-comfy"

    def __init__(
        self,
        *,
        online: bool = True,
        version: str = "0.37.0",
        workflow: dict | None = None,
        binding: dict | None = None,
        binding_error: EngineError | None = None,
    ) -> None:
        self.online = online
        self.version = version
        self.workflow = workflow or WORKFLOW
        self.binding = binding or BINDING
        self.binding_error = binding_error

    async def health(self) -> EngineStatus:
        return EngineStatus(
            online=self.online,
            detail="ok" if self.online else "offline",
            engine_name="comfyui",
            engine_version=self.version,
        )

    def load_binding(self, ref: EngineBindingRef):
        if self.binding_error is not None:
            raise self.binding_error
        return self.workflow, self.binding, "wfhash", "bhash"


def make_http(
    *, nodes: set[str] | None = None, models: dict[str, list[str]] | None = None,
    fail_paths: set[str] | None = None,
):
    registered = set(nodes) if nodes is not None else {str(n["class_type"]) for n in WORKFLOW.values()}
    files = models or MODELS
    fail = fail_paths or set()
    calls: list[str] = []

    def get(base: str, path: str, timeout: float):
        calls.append(path)
        if path in fail:
            return None
        if path.startswith("/object_info/"):
            class_type = path.rsplit("/", 1)[-1]
            return (200, {class_type: {}}) if class_type in registered else (404, None)
        if path.startswith("/models/"):
            folder = path.rsplit("/", 1)[-1]
            return (200, list(files.get(folder, [])))
        return (404, None)

    return get, calls


def module_identity(module_id: str = "basic_generate") -> dict:
    return {
        "module_id": module_id,
        "module_version": "v1",
        "provider": "comfyui",
        "binding_version": "v1",
        "workflow_hash": "wfhash",
        "binding_hash": "bhash",
    }


def service(settings: Settings, adapter, http_get=None) -> RuntimePreflightService:
    preflight.reset_preflight_cache()
    return RuntimePreflightService(settings, adapter, http_get=http_get)


def test_ready_when_nodes_and_models_present(settings):
    http, _calls = make_http()
    result = service(settings, FakeComfyAdapter(), http).check_modules([module_identity()])
    assert result["status"] == "READY"
    assert result["engine"]["online"] is True
    module = result["modules"][0]
    assert module["missing_nodes"] == [] and module["missing_models"] == []


def test_missing_node_blocks(settings):
    http, _calls = make_http(nodes={
        str(n["class_type"]) for n in WORKFLOW.values() if n["class_type"] != "KSampler"
    })
    result = service(settings, FakeComfyAdapter(), http).check_modules([module_identity()])
    assert result["status"] == "BLOCKED"
    assert "KSampler" in result["modules"][0]["missing_nodes"]


def test_missing_model_blocks(settings):
    models = {**MODELS, "loras": []}
    http, _calls = make_http(models=models)
    result = service(settings, FakeComfyAdapter(), http).check_modules([module_identity()])
    assert result["status"] == "BLOCKED"
    assert result["modules"][0]["missing_models"] == [
        {"folder": "loras", "filename": "turbo.safetensors"}
    ]


def test_engine_offline_is_unknown(settings):
    http, calls = make_http()
    result = service(settings, FakeComfyAdapter(online=False), http).check_modules([module_identity()])
    assert result["status"] == "UNKNOWN"
    assert result["modules"][0]["unknown_reasons"] == ["engine_offline"]
    assert calls == [], "引擎离线时不应继续请求节点/模型接口"


def test_binding_hash_mismatch_is_rejected(settings):
    adapter = FakeComfyAdapter(binding_error=EngineError("BINDING_HASH_MISMATCH", "hash mismatch"))
    result = service(settings, adapter, make_http()[0]).check_modules([module_identity()])
    assert result["status"] == "UNKNOWN"
    assert "BINDING_HASH_MISMATCH" in result["modules"][0]["unknown_reasons"][0]


def test_unknown_model_loader_is_unknown(settings):
    workflow = {**WORKFLOW, "9": {"class_type": "CustomModelLoader", "inputs": {"model": "x.bin"}}}
    adapter = FakeComfyAdapter(workflow=workflow)
    nodes = {str(node["class_type"]) for node in workflow.values()}
    result = service(settings, adapter, make_http(nodes=nodes)[0]).check_modules([module_identity()])
    assert result["status"] == "UNKNOWN"
    assert any("CustomModelLoader" in reason for reason in result["modules"][0]["unknown_reasons"])


def test_preflight_cache_hit_and_ttl_refresh(settings, monkeypatch):
    monkeypatch.setattr(preflight, "SYSTEM_TTL_SECONDS", 0.01)
    monkeypatch.setattr(preflight, "NODE_TTL_SECONDS", 0.01)
    monkeypatch.setattr(preflight, "MODEL_TTL_SECONDS", 0.01)
    http, calls = make_http()
    svc = service(settings, FakeComfyAdapter(), http)
    first = svc.check_modules([module_identity()])
    assert first["cache_hit"] is False
    count_after_first = len(calls)
    second = svc.check_modules([module_identity()])
    assert second["cache_hit"] is True
    assert len(calls) == count_after_first
    time.sleep(0.05)
    third = svc.check_modules([module_identity()])
    assert third["cache_hit"] is False
    assert len(calls) > count_after_first


def test_multi_module_pipeline_checked(settings):
    http, calls = make_http()
    result = service(settings, FakeComfyAdapter(), http).check_modules([
        module_identity("basic_generate"), module_identity("upscale"),
    ])
    assert result["status"] == "READY"
    assert [item["module_id"] for item in result["modules"]] == ["basic_generate", "upscale"]
    assert "/object_info/KSampler" in calls


def test_version_below_minimum_blocks(settings):
    result = service(
        settings, FakeComfyAdapter(version="0.30.0"), make_http()[0]
    ).check_modules([module_identity()])
    assert result["status"] == "BLOCKED"
    assert any("ComfyUI 版本不满足" in reason for reason in result["modules"][0]["missing_requirements"])


def test_all_formal_bindings_model_loaders_have_rules():
    """静态测试：当前所有正式 Binding 的模型加载节点都必须有解析规则。"""
    known = set(preflight.MODEL_LOADERS)
    for path in sorted((ROOT / "workflows/providers/comfyui").glob("*/*/workflow.json")):
        workflow = json.loads(path.read_text(encoding="utf-8"))
        for node in workflow.values():
            class_type = str((node or {}).get("class_type") or "")
            if "Loader" in class_type:
                assert class_type in known, f"{path}: 未覆盖的模型加载节点 {class_type}"


def _mock_settings(settings: Settings) -> Settings:
    return dataclasses.replace(
        settings,
        workflow=WorkflowConfig(raw={"engine": {"provider": "mock", "options": {
            "worker_poll_interval_ms": 20, "engine_poll_ms": 20,
        }}}),
        agent={},
    )


def mock_client(settings):
    app = create_app(_mock_settings(settings))
    return TestClient(app)


def test_preflight_api_mock_engine_ready(settings):
    with mock_client(settings) as client:
        response = client.post("/api/v1/engine/preflight", json={"module_ids": ["basic_generate"]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "READY"
        assert body["modules"][0]["module_id"] == "basic_generate"
        assert body["modules"][0]["notes"] == ["mock engine：跳过真实依赖检测"]


def test_preflight_api_with_comfyui_adapter(settings, monkeypatch):
    """服务端重新解析真实身份 → 使用 ComfyUIAdapter → 动态检测（HTTP 全 Mock）。"""
    http, _calls = make_http()
    monkeypatch.setattr(preflight, "_http_get_json", http)
    preflight.reset_preflight_cache()
    app = create_app(settings)
    with TestClient(app) as client:
        client.app.state.adapter = FakeComfyAdapter()
        response = client.post("/api/v1/engine/preflight", json={"module_ids": ["basic_generate"]})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "READY"
        assert body["modules"][0]["workflow_hash"] == "wfhash"
        assert body["modules"][0]["binding_hash"] == "bhash"


def _blocked_result() -> dict:
    return {
        "status": "BLOCKED",
        "engine": {"online": True, "version": "0.37.0", "detail": ""},
        "modules": [{
            "module_id": "basic_generate", "binding_version": "v1",
            "workflow_hash": "wf", "binding_hash": "bh", "status": "BLOCKED",
            "missing_nodes": [], "missing_models": [{"folder": "loras", "filename": "x.safetensors"}],
            "missing_requirements": [], "unknown_reasons": [], "notes": [], "cache_hit": False,
        }],
        "checked_at": "2026-03-01T00:00:00Z",
        "cache_hit": False,
    }


def test_jobs_gate_blocks_without_prompt_or_job(settings, session, monkeypatch):
    monkeypatch.setattr(
        preflight.RuntimePreflightService, "check_modules",
        lambda self, modules: _blocked_result(),
    )
    app = create_app(settings)  # 默认 comfyui provider；检测被 Mock 为 BLOCKED
    before = (session.query(Prompt).count(), session.query(Job).count(), session.query(JobStage).count())
    with TestClient(app) as client:
        response = client.post("/api/v1/jobs", json={
            "source": "web",
            "client_request_id": "w20-blocked",
            "snapshot": {
                "prompt_mode": "full", "full_prompt": "gate test", "negative_prompt": "",
                "width": 768, "height": 768, "count": 1, "seed_mode": "random",
                "workflow_modules": [],
            },
        })
        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "RUNTIME_PREFLIGHT_BLOCKED"
        assert (
            session.query(Prompt).count(), session.query(Job).count(), session.query(JobStage).count()
        ) == before


def test_agent_gate_blocks_without_prompt_or_job(settings, session, monkeypatch):
    monkeypatch.setenv(ENV_AGENT_TOKEN, "w20-token")
    monkeypatch.setattr(
        preflight.RuntimePreflightService, "check_modules",
        lambda self, modules: _blocked_result(),
    )
    app = create_app(settings)
    before = (session.query(Prompt).count(), session.query(Job).count(), session.query(JobStage).count())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agent/jobs",
            json={"prompt": "agent gate test", "module_id": "basic_generate"},
            headers={"Authorization": "Bearer w20-token"},
        )
        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "RUNTIME_PREFLIGHT_BLOCKED"
        assert (
            session.query(Prompt).count(), session.query(Job).count(), session.query(JobStage).count()
        ) == before


def test_run_preflight_raises_validation_error(settings):
    from app.core.errors import ValidationError

    preflight.reset_preflight_cache()
    with pytest.raises(ValidationError) as exc:
        run_preflight(settings, FakeComfyAdapter(online=False), [module_identity()])
    assert exc.value.code == "RUNTIME_PREFLIGHT_UNKNOWN"
