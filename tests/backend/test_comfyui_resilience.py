"""ComfyUIAdapter 掉线语义与 binding 版本解析测试（Phase 2.1 §二、§七）。

全部离线可跑（CI 安全）：用 stub 替身注入 httpx 响应/异常，不依赖真实 ComfyUI。
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

import httpx
import pytest

from app.engine import comfyui as comfyui_module
from app.engine.base import EngineError
from app.engine.comfyui import MISSING_TOLERANCE, ComfyUIAdapter


class StubResponse:
    def __init__(self, payload: dict | None = None, status_code: int = 200):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "stub error", request=httpx.Request("GET", "http://stub"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> dict:
        return self._payload


class StubClient:
    def __init__(self, handler, calls: list):
        self._handler = handler
        self._calls = calls

    async def __aenter__(self) -> "StubClient":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def get(self, url: str, **kwargs) -> StubResponse:
        self._calls.append(("GET", url))
        return self._handler(url, method="GET")

    async def post(self, url: str, json=None, **kwargs) -> StubResponse:
        self._calls.append(("POST", url, json))
        return self._handler(url, method="POST", json=json)


def install_stub(monkeypatch, handler, calls: list | None = None) -> list:
    """安装 httpx AsyncClient 替身；calls 记录 ("GET"/"POST", url[, payload])。"""
    recorded: list = calls if calls is not None else []
    monkeypatch.setattr(
        comfyui_module.httpx, "AsyncClient", lambda **kwargs: StubClient(handler, recorded)
    )
    return recorded


def make_adapter() -> ComfyUIAdapter:
    return ComfyUIAdapter({}, {"url": "http://stub"})


# ===== §二：history 请求失败不得伪装成“还在运行” =====

def test_history_connect_error_raises_engine_offline(monkeypatch):
    def handler(url: str, **_kwargs):
        raise httpx.ConnectError("connection refused")

    install_stub(monkeypatch, handler)
    adapter = make_adapter()
    with pytest.raises(EngineError) as excinfo:
        import asyncio

        asyncio.run(adapter.get_job_status("prompt-1"))
    assert excinfo.value.error_type == "ENGINE_OFFLINE"


def test_history_http_error_raises_transient_network(monkeypatch):
    def handler(url: str, **_kwargs):
        raise httpx.ReadTimeout("read timeout")

    install_stub(monkeypatch, handler)
    adapter = make_adapter()
    with pytest.raises(EngineError) as excinfo:
        import asyncio

        asyncio.run(adapter.get_job_status("prompt-1"))
    assert excinfo.value.error_type == "ENGINE_NETWORK"
    assert excinfo.value.transient is True, "瞬时网络错误必须可被 Worker 有限重试"


def test_history_absent_but_queued_is_running_not_failed(monkeypatch):
    """history 尚无该 prompt（普通"还没跑完"）不得误判失败。"""
    def handler(url: str, **_kwargs):
        if "/history/" in url:
            return StubResponse({})  # 可达但任务未出现在 history
        return StubResponse({"queue_running": [[1, "prompt-1", {}, {}, []]], "queue_pending": []})

    install_stub(monkeypatch, handler)
    adapter = make_adapter()
    import asyncio

    status = asyncio.run(adapter.get_job_status("prompt-1"))
    assert status.state == "running"


def test_lost_task_becomes_unknown_after_bounded_polls(monkeypatch):
    """既不在 /queue 也不在 /history（引擎重启丢失任务）→ 有界轮询后 unknown，不得永久 RUNNING。"""
    def handler(url: str, **_kwargs):
        if "/history/" in url:
            return StubResponse({})
        return StubResponse({"queue_running": [], "queue_pending": []})

    install_stub(monkeypatch, handler)
    adapter = make_adapter()
    adapter._live["prompt-1"] = {
        "stage": "sampling", "progress": 0.5, "state": "running",
        "error_type": "", "error_message": "", "updated": time.monotonic() - 10_000,  # stale 实时层
    }
    import asyncio

    states = [asyncio.run(adapter.get_job_status("prompt-1")).state for _ in range(MISSING_TOLERANCE)]
    assert states[-2] == "running" and states[-1] == "unknown", \
        f"容忍期内保持 running，超限后必须 unknown：{states}"


def test_fresh_live_state_keeps_waiting(monkeypatch):
    """实时层新鲜（WS 仍在推送）且不在队列/history → 继续 running（不误判丢失）。"""
    def handler(url: str, **_kwargs):
        if "/history/" in url:
            return StubResponse({})
        return StubResponse({"queue_running": [], "queue_pending": []})

    install_stub(monkeypatch, handler)
    adapter = make_adapter()
    adapter._live["prompt-1"] = {
        "stage": "sampling", "progress": 0.4, "state": "running",
        "error_type": "", "error_message": "", "updated": time.monotonic(),
    }
    import asyncio

    for _ in range(MISSING_TOLERANCE + 3):
        status = asyncio.run(adapter.get_job_status("prompt-1"))
        assert status.state == "running", "WS 新鲜时不得判定任务丢失"


# ===== §七（Phase 2.1）：binding 版本由 module_id + binding_version 解析（Phase 3 §0.2 动态绑定） =====

def test_binding_version_switchable(tmp_path, monkeypatch):
    """v1 可加载；把同一 binding 复制为 v2 后，请求 binding_version=v2 即可切换。"""
    from app.engine.base import EngineBindingRef

    source = Path(comfyui_module.PROVIDERS_DIR) / "basic_generate" / "v1"
    target = tmp_path / "basic_generate" / "v2"
    shutil.copytree(source, target)
    binding_text = (target / "binding.yaml").read_text(encoding="utf-8")
    (target / "binding.yaml").write_text(
        binding_text.replace("binding_version: v1", "binding_version: v2"), encoding="utf-8"
    )
    monkeypatch.setattr(comfyui_module, "PROVIDERS_DIR", tmp_path)

    adapter = ComfyUIAdapter({}, {"url": "http://stub"})
    _workflow, binding, workflow_hash = adapter.load_binding(EngineBindingRef(
        module_id="basic_generate", provider="comfyui", binding_version="v2",
    ))
    assert str(binding["binding_version"]) == "v2"
    assert workflow_hash, "v2 binding 必须可加载并计算出 workflow_hash"
    assert ComfyUIAdapter.binding_dir("basic_generate", "v2") == target


def test_missing_binding_version_raises_binding_not_found(tmp_path, monkeypatch):
    from app.engine.base import EngineBindingRef

    monkeypatch.setattr(comfyui_module, "PROVIDERS_DIR", tmp_path)
    adapter = ComfyUIAdapter({}, {"url": "http://stub"})
    with pytest.raises(EngineError) as excinfo:
        adapter.load_binding(EngineBindingRef(
            module_id="basic_generate", provider="comfyui", binding_version="v9",
        ))
    assert excinfo.value.error_type == "BINDING_NOT_FOUND"


# ===== §四（Phase 2.2）：取消不得误伤其他 ComfyUI 任务 =====

def test_cancel_pending_target_only_deletes(monkeypatch):
    """target 在 pending → 只 delete，绝不调用全局 /interrupt。"""
    def handler(url: str, **_kwargs):
        if url.endswith("/queue"):
            return StubResponse({"queue_running": [[1, "other-prompt", {}, {}, []]],
                                 "queue_pending": [[2, "target", {}, {}, []]]})
        return StubResponse({})

    calls = install_stub(monkeypatch, handler)
    import asyncio

    assert asyncio.run(make_adapter().cancel_job("target")) is True
    posts = [call for call in calls if call[0] == "POST"]
    assert [call[1] for call in posts] == ["http://stub/queue"], "pending 目标只允许 delete"
    assert posts[0][2] == {"delete": ["target"]}
    assert not any("interrupt" in call[1] for call in calls), "pending 目标不得触发 /interrupt"


def test_cancel_running_target_allowed_to_interrupt(monkeypatch):
    """target 正是当前 running → 才允许 /interrupt。"""
    def handler(url: str, **_kwargs):
        if url.endswith("/queue"):
            return StubResponse({"queue_running": [[1, "target", {}, {}, []]], "queue_pending": []})
        return StubResponse({})

    calls = install_stub(monkeypatch, handler)
    import asyncio

    assert asyncio.run(make_adapter().cancel_job("target")) is True
    assert any("interrupt" in call[1] for call in calls), "running 目标必须请求 /interrupt"


def test_cancel_other_running_prompt_never_interrupted(monkeypatch):
    """当前 running 是别的 prompt（用户手工任务）→ 禁止 /interrupt、禁止任何队列写操作。"""
    def handler(url: str, **_kwargs):
        if url.endswith("/queue"):
            return StubResponse({"queue_running": [[1, "someone-elses", {}, {}, []]],
                                 "queue_pending": []})
        return StubResponse({})

    calls = install_stub(monkeypatch, handler)
    import asyncio

    assert asyncio.run(make_adapter().cancel_job("target")) is False
    assert not any("interrupt" in call[1] for call in calls), "不得打断其他任务"
    assert not any(call[0] == "POST" for call in calls), "目标不在队列时不应写队列"