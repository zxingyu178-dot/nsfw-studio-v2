"""JSON 结构化日志（Phase 0 规范 §十一）。

文件布局（位于 DataRoot 下）：

- ``logs/app/app.log``    ：INFO+，全量应用日志（root logger）
- ``logs/jobs/jobs.log``  ：任务日志（logger 名 ``studio.jobs``，同时冒泡进 app.log）
- ``logs/errors/error.log``：ERROR+

格式为 JSON Lines：``{"time","level","module","message"}``，异常时附 ``exc`` 字段。
文件按 5MB 轮转，保留 5 份。
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

JOBS_LOGGER_NAME = "studio.jobs"

_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _make_file_handler(path: Path, level: int) -> RotatingFileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(JsonFormatter())
    return handler


def setup_logging(data_root: Path, console_level: str = "INFO") -> None:
    """初始化全局日志（幂等，可重复调用）。"""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # 重新初始化时先移除旧 handler，避免重复输出与文件句柄泄漏
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(getattr(logging, console_level.upper(), logging.INFO))
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s"))
    root.addHandler(console)

    root.addHandler(_make_file_handler(data_root / "logs" / "app" / "app.log", logging.INFO))
    root.addHandler(_make_file_handler(data_root / "logs" / "errors" / "error.log", logging.ERROR))

    jobs = logging.getLogger(JOBS_LOGGER_NAME)
    for handler in list(jobs.handlers):
        jobs.removeHandler(handler)
        handler.close()
    jobs.addHandler(_make_file_handler(data_root / "logs" / "jobs" / "jobs.log", logging.INFO))
    jobs.propagate = True  # 任务事件同时进入 app 全量日志
