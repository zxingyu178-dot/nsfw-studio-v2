"""关闭真实SSE并排空普通请求；只使用临时回环端口，不启动业务/DataRoot。"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import http.client
import socket
import threading
import time
from types import SimpleNamespace

from fastapi import FastAPI
import uvicorn

from app.api.v1.jobs import job_events
from app.core.events import EventBroker


def test_close_wakes_full_empty_and_late_subscribers():
    async def scenario():
        broker = EventBroker()
        broker.attach_loop(asyncio.get_running_loop())
        full, empty = broker.subscribe(), broker.subscribe()
        for _ in range(full.maxsize):
            full.put_nowait('old event')
        broker.publish({'queued_before_close': True})
        broker.close()
        broker.close()
        broker.publish({'ignored': True})
        await asyncio.sleep(0)
        assert await asyncio.wait_for(full.get(), 1) is None
        assert full.empty()
        assert await asyncio.wait_for(empty.get(), 1) is None
        late = broker.subscribe()
        assert await asyncio.wait_for(late.get(), 1) is None
        broker.unsubscribe(full)
        broker.unsubscribe(empty)
        assert broker.subscriber_count() == 0

    asyncio.run(scenario())


def test_actual_sse_finishes_and_unsubscribes_on_broker_close():
    async def scenario():
        broker = EventBroker()
        broker.attach_loop(asyncio.get_running_loop())

        class Request:
            app = SimpleNamespace(state=SimpleNamespace(events=broker))

            async def is_disconnected(self):
                return False

        response = await job_events(Request())
        stream = response.body_iterator
        assert await anext(stream) == ': connected\n\n'
        broker.close()
        assert await asyncio.wait_for(anext(stream, None), 1) is None
        assert broker.subscriber_count() == 0

    asyncio.run(scenario())


def test_shutdown_ends_sse_but_waits_for_ordinary_request_before_lifespan():
    from app.runtime_server import StudioServer

    broker = EventBroker()
    stopped = threading.Event()
    ordinary_started = threading.Event()
    ordinary_release = threading.Event()
    ordinary_result = []

    @asynccontextmanager
    async def lifespan(app):
        broker.attach_loop(asyncio.get_running_loop())
        yield
        stopped.set()

    app = FastAPI(lifespan=lifespan)
    app.state.events = broker
    app.add_api_route('/events', job_events)

    @app.get('/ordinary')
    async def ordinary():
        ordinary_started.set()
        while not ordinary_release.is_set():
            await asyncio.sleep(.01)
        return {'finished': True}

    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(8)
    port = sock.getsockname()[1]
    server = StudioServer(uvicorn.Config(app, log_level='warning', lifespan='on'), application=app)
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    stream_client = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
    response = None

    def ordinary_client():
        client = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        try:
            client.request('GET', '/ordinary')
            result = client.getresponse()
            ordinary_result.append((result.status, result.read()))
        finally:
            client.close()

    reader = threading.Thread(target=ordinary_client, daemon=True)
    try:
        thread.start()
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.01)
        assert server.started
        stream_client.request('GET', '/events')
        response = stream_client.getresponse()
        assert response.readline().strip() == b': connected'
        reader.start()
        assert ordinary_started.wait(3)
        server.should_exit = True
        assert response.read().strip() == b''  # 不需客户端断开，SSE自己正常结束。
        assert not stopped.is_set()  # 普通请求尚未完成，不能提前清理后台。
        ordinary_release.set()
        reader.join(3)
        thread.join(3)
        assert ordinary_result == [(200, b'{"finished":true}')]
        assert not thread.is_alive()
        assert stopped.is_set()
        assert broker.subscriber_count() == 0
    finally:
        ordinary_release.set()
        if response is not None:
            response.close()
        stream_client.close()
        server.should_exit = True
        if thread.is_alive():
            server.force_exit = True  # 仅隔离测试自己的线程，不操作生产进程。
            thread.join(3)
        if reader.ident is not None:
            reader.join(3)
        sock.close()
