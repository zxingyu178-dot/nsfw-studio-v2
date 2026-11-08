"""Windows真实CTRL_BREAK；隐藏的隔离子进程，仅用临时回环端口/文件。"""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest


_CHILD = '''
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import socket
import sys
from fastapi import FastAPI
import uvicorn
from app.api.v1.jobs import job_events
from app.core.events import EventBroker
from app.runtime_server import StudioServer

root = Path(sys.argv[1])
broker = EventBroker()
@asynccontextmanager
async def lifespan(app):
    broker.attach_loop(asyncio.get_running_loop())
    yield
    (root / 'cleaned.json').write_text(json.dumps({'subscribers': broker.subscriber_count()}))
app = FastAPI(lifespan=lifespan)
app.state.events = broker
app.add_api_route('/events', job_events)
sock = socket.socket()
sock.bind(('127.0.0.1', 0))
sock.listen(8)
(root / 'ready.tmp').write_text(json.dumps({'port': sock.getsockname()[1]}))
(root / 'ready.tmp').replace(root / 'ready.json')
StudioServer(uvicorn.Config(app, log_level='info', lifespan='on'), application=app).run(sockets=[sock])
'''

_SIGNAL = '''
import ctypes
import sys
k = ctypes.WinDLL('kernel32', use_last_error=True)
k.FreeConsole()
if not k.AttachConsole(int(sys.argv[1])):
    raise ctypes.WinError(ctypes.get_last_error())
try:
    if not k.GenerateConsoleCtrlEvent(1, int(sys.argv[1])):
        raise ctypes.WinError(ctypes.get_last_error())
finally:
    k.FreeConsole()
'''


@pytest.mark.skipif(os.name != 'nt', reason='需要Windows控制台信号')
def test_windows_ctrl_break_drains_live_sse_and_finishes_lifespan(tmp_path):
    helper = tmp_path / 'server.py'
    helper.write_text(_CHILD, encoding='utf-8')
    project = Path(__file__).resolve().parents[2]
    env = dict(os.environ, PYTHONPATH=str(project / 'backend'),
               NSFW_STUDIO_DATA_ROOT=str(tmp_path / 'unused-data'))
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    response = None
    client = None
    log_path = tmp_path / 'server.log'
    with log_path.open('w', encoding='utf-8') as log:
        child = subprocess.Popen(
            [sys.executable, str(helper), str(tmp_path)], cwd=project, env=env,
            stdout=log, stderr=subprocess.STDOUT, startupinfo=startup,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE,
        )
        try:
            deadline = time.monotonic() + 15
            ready = tmp_path / 'ready.json'
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            assert ready.exists(), '隔离服务未提供临时端口'
            port = json.loads(ready.read_text())['port']
            while time.monotonic() < deadline:
                client = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
                try:
                    client.request('GET', '/events')
                    response = client.getresponse()
                    break
                except ConnectionRefusedError:
                    client.close()
                    time.sleep(.02)
            assert response is not None
            assert response.readline().strip() == b': connected'
            stopping_at = time.monotonic()
            signal_result = subprocess.run(
                [sys.executable, '-c', _SIGNAL, str(child.pid)],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            assert signal_result.returncode == 0, signal_result.stderr
            assert response.read().strip() == b''
            child.wait(timeout=8)
            assert json.loads((tmp_path / 'cleaned.json').read_text()) == {'subscribers': 0}
            assert 'Traceback (most recent call last)' not in log_path.read_text(encoding='utf-8')
            (tmp_path / 'signal-result.json').write_text(json.dumps({
                'exit_code': child.returncode, 'sse_eof': True, 'lifespan_cleaned': True,
                'stop_seconds': round(time.monotonic() - stopping_at, 3),
            }), encoding='utf-8')
        finally:
            if response is not None:
                response.close()
            if client is not None:
                client.close()
            if child.poll() is None:
                child.kill()  # 仅终止本测试自己创建的精确Popen子进程。
                child.wait(timeout=5)
