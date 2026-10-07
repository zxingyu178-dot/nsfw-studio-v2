"""后端测试夹具：全部用例使用临时 DataRoot，绝不触碰真实数据目录。"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, load_settings
from app.main import create_app
from app.services.system_service import bootstrap


@pytest.fixture()
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("NSFW_STUDIO_DATA_ROOT", str(tmp_path / "data"))
    return load_settings()


@pytest.fixture()
def client(settings: Settings):
    app = create_app(settings)
    with TestClient(app) as test_client:  # 进入上下文时触发 lifespan（启动引导）
        yield test_client


@pytest.fixture()
def session_factory(settings: Settings) -> Iterator[sessionmaker]:
    """服务层测试用：初始化数据库并返回 session 工厂。"""
    bootstrap(settings)
    from app.database.base import make_engine, make_session_factory

    engine = make_engine(settings.storage.database_path)
    yield make_session_factory(engine)
    engine.dispose()


@pytest.fixture()
def session(session_factory) -> Iterator[Session]:
    with session_factory() as db_session:
        yield db_session


@pytest.fixture()
def png_bytes() -> bytes:
    """最小合法 PNG（1x1 透明像素）。"""
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d494844520000000100000001080600000"
        "01f15c4890000000d49444154789c6260000000060005"
        "27de3bbb0000000049454e44ae426082"
    )
