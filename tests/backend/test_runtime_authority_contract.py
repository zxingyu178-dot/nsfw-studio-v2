"""Runtime Authority 合同测试（Phase 0.14 Runtime Closure）。

锁定：
- config.engine_runtime.mode 默认 = controlhub（生产）；
- Engine（生图引擎）适配器的 integration_id 恒为 comfyui，绝不允许 nsfw-studio-v2；
- CLI 命令构造正确（解释器 / 模块 / 动作 / --data-root，且 --data-root 在 id 之后）；
- mode=direct 才退回 v0.13.2 直接 Popen 适配器。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import engine_runtime_service as ers
from app.services.controlhub_lifecycle import ControlHubLifecycleClient
from app.services.engine_runtime_service import (
    ControlHubEngineRuntime,
    EngineRuntimeService,
    create_engine_runtime,
)


def _settings(tmp_path: Path, **engine_runtime_over) -> SimpleNamespace:
    return SimpleNamespace(
        storage=SimpleNamespace(data_root=tmp_path / "data"),
        engine_runtime={"host": "127.0.0.1", "port": 8188, **engine_runtime_over},
        controlhub={},
    )


def test_default_mode_is_controlhub(tmp_path):
    """生产默认：未指定 mode 时走 ControlHub 适配器（而非直接 Popen）。"""
    svc = create_engine_runtime(_settings(tmp_path))
    assert isinstance(svc, ControlHubEngineRuntime)
    assert not isinstance(svc, EngineRuntimeService)


def test_direct_mode_returns_direct_adapter(tmp_path):
    """mode=direct 才保留 v0.13.2 直接 Popen 实现（scripts/dev 专用）。"""
    svc = create_engine_runtime(_settings(tmp_path, mode="direct"))
    assert isinstance(svc, EngineRuntimeService)
    assert not isinstance(svc, ControlHubEngineRuntime)


def test_engine_target_defaults_to_comfyui(tmp_path):
    """生图引擎 integration_id 默认 = comfyui。"""
    svc = ControlHubEngineRuntime(_settings(tmp_path))
    assert svc.integration_id == "comfyui"


def test_engine_refuses_nsfw_studio_v2_target(tmp_path):
    """合同红线：engine 绝不允许被指向 nsfw-studio-v2（Studio 后端，非引擎）。"""
    with pytest.raises(RuntimeError):
        ControlHubEngineRuntime(_settings(tmp_path, integration_id="nsfw-studio-v2"))


def test_controlhub_client_argv_order(tmp_path):
    """CLI argv 冻结顺序：-m MODULE action id --data-root path（--data-root 在 id 之后）。"""
    client = ControlHubLifecycleClient("PY", "DATA_ROOT")
    argv = client.build_argv("start", "comfyui")
    assert argv == [
        "PY", "-m", "control_hub.lifecycle_cli",
        "start", "comfyui",
        "--data-root", "DATA_ROOT",
    ]


def test_engine_module_does_not_target_nsfw_studio_v2():
    """静态合同守卫：engine 服务模块源码不把 nsfw-studio-v2 作为 engine 启停目标。

    仅允许 nsfw-studio-v2 出现在"禁止性注释/合同常量/Studio 自身"语境；
    engine 适配器默认 integration_id 必须是 comfyui（已在上面用例锁定）。
    """
    src = Path(ers.__file__).read_text(encoding="utf-8")
    # ControlHubEngineRuntime.__init__ 中的合同断言必须显式拒绝 nsfw-studio-v2
    assert 'integration_id == STUDIO_INTEGRATION_ID' in src
    assert 'STUDIO_INTEGRATION_ID' in src
