"""后端测试夹具：全部用例使用临时 DataRoot，绝不触碰真实数据目录。"""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

# ===== Hermetic 护栏（v0.13.2 事故教训） =====
# 测试全程强制 hermetic：绝不允许任何测试进程向真实 127.0.0.1:8188 / 8000 / 8767 发起连接或 POST。
# - 置位 NSFW_STUDIO_HERMETIC=1，供真实集成测试自检并 skip；
# - 清空代理 env，避免 httpx 因 socks 代理在构造期报错（干扰护栏验证）；
# - 包一层 httpx Client/AsyncClient.send，凡目标是这些端口的请求直接抛错（fail fast）。
os.environ["NSFW_STUDIO_HERMETIC"] = "1"
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"

_BLOCKED_HOSTS_PORTS = {(("127.0.0.1"), p) for p in (8188, 8000, 8767)}


def _install_httpx_guard() -> None:
    """在 Client/AsyncClient.send 层拦截到真实 8188/8000/8767 的请求（最可靠）。"""
    try:
        import httpx
    except Exception:
        return

    def _block(request):
        host = request.url.host
        port = request.url.port
        if (host, port) in _BLOCKED_HOSTS_PORTS:
            raise RuntimeError(
                f"[hermetic guard] 测试禁止连接真实 {host}:{port} "
                f"（method={request.method} url={request.url}）"
            )

    orig_send = httpx.Client.send
    def send_guarded(self, request, **kw):  # noqa: ANN001
        _block(request)
        return orig_send(self, request, **kw)
    httpx.Client.send = send_guarded

    orig_async_send = httpx.AsyncClient.send
    async def async_send_guarded(self, request, **kw):  # noqa: ANN001
        _block(request)
        return await orig_async_send(self, request, **kw)
    httpx.AsyncClient.send = async_send_guarded


_install_httpx_guard()

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


@pytest.fixture()
def mobile_client(settings: Settings):
    """Mobile Review Bridge 独立 app 的 TestClient（与 Desktop 8000 完全隔离）。"""
    from app.mobile_main import create_mobile_app

    app = create_mobile_app(settings)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def make_mobile_image(session_factory, settings):
    """在共享 DB 里造一张 status=NEW 的图（手机/桌面桥共用同一 ImageReviewSessionService）。"""
    from app.services import image_service
    from app.storage.manager import StorageManager

    def _make(count: int = 1):
        from PIL import Image as PILImage
        import io
        storage = StorageManager(settings)
        images = []
        with session_factory() as session:
            for i in range(count):
                buf = io.BytesIO()
                PILImage.new("RGB", (800 + i, 600), (10 + i, 20, 30)).save(buf, format="PNG")
                img = image_service.import_engine_output(
                    session, storage, data=buf.getvalue(),
                    original_filename=f"img{i}.png", source="comfyui",
                )
                images.append(img)
        return images

    return _make
