"""同一Studio服务的Uvicorn入口：先结束SSE，再排空普通请求和执行lifespan。"""
from __future__ import annotations

import socket

from fastapi import FastAPI
import uvicorn


class StudioServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config, *, application: FastAPI) -> None:
        super().__init__(config)
        self.application = application

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        # lifespan清理发生在Uvicorn等待活动连接之后，不能等到那里才关闭SSE。
        broker = getattr(self.application.state, "events", None)
        if broker is not None:
            broker.close()
        await super().shutdown(sockets=sockets)


def main() -> None:
    from app.main import app

    server = StudioServer(
        uvicorn.Config(app, host="127.0.0.1", port=8000), application=app,
    )
    server.run()


if __name__ == "__main__":
    main()
