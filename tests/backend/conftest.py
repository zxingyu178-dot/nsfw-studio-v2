"""后端测试夹具：全部用例使用临时 DataRoot，绝不触碰真实数据目录。"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, load_settings
from app.main import create_app


@pytest.fixture()
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("NSFW_STUDIO_DATA_ROOT", str(tmp_path / "data"))
    return load_settings()


@pytest.fixture()
def client(settings: Settings):
    app = create_app(settings)
    with TestClient(app) as test_client:  # 进入上下文时触发 lifespan（启动引导）
        yield test_client
