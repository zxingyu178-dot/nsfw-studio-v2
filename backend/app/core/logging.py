"""JSON 结构化日志（Phase 0 规范 §十一）。

文件布局（位于 DataRoot 下）：

- ``logs/app/app.log``    ：INFO+，全量应用日志（root logger）
- ``logs/jobs/jobs.log``  ：任务日志（logger 名 ``studio.jobs``，同时冒泡进 app.log）
- ``logs/errors/error.log``：ERROR+

格式为 JSON Lines：``{"time","level","module","message"}``，异常时附 ``exc`` 字段。
文件按 5MB 轮转，保留 5 份。

``profile="mobile"`` 时写入独立目录 ``logs/mobile/``：Mobile Bridge 是独立进程，
与主后端共用同一日志文件会让 Windows 上的轮转 rename 失败（PermissionError），
失败后的每条日志都会把完整 traceback 刷进 stdout。
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
_LOG_PROFILES = {
    "main": ("app", "errors", "jobs"),
    "mobile": ("mobile", "mobile", None),
}


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


class _SafeRotatingFileHandler(RotatingFileHandler):
    """轮转/写盘失败不致命，且只提示一次。

    Windows 上日志文件被其它进程占用时，``doRollover`` 的 rename 会抛 OSError；
    标准库 ``handleError`` 会对每条日志打印一次完整 traceback，导致调用方的
    stdout 重定向文件（runtime/logs/app.log）爆炸式增长。这里统一静默为一次提示。
    """

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("delay", True)  # 延迟到首条日志再打开文件，减少启动期句柄冲突
        self._error_reported = False
        super().__init__(*args, **kwargs)

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except OSError as error:  # 轮转失败：继续追加当前文件
            self._report(error)

    def handleError(self, record: logging.LogRecord) -> None:
        self._report(sys.exc_info()[1])

    def _report(self, error) -> None:
        if self._error_reported:
            return
        self._error_reported = True
        try:
            sys.stderr.write(f"[logging] 日志文件写入/轮转失败（后续同类错误不再提示）: {error}\n")
        except Exception:
            pass


def _make_file_handler(path: Path, level: int) -> RotatingFileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = _SafeRotatingFileHandler(path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(JsonFormatter())
    return handler


def setup_logging(data_root: Path, console_level: str = "INFO", *, profile: str = "main") -> None:
    """初始化全局日志（幂等，可重复调用）；profile 决定日志文件目录。"""
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

    app_dir, error_dir, jobs_dir = _LOG_PROFILES.get(profile, _LOG_PROFILES["main"])
    root.addHandler(_make_file_handler(data_root / "logs" / app_dir / "app.log", logging.INFO))
    root.addHandler(_make_file_handler(data_root / "logs" / error_dir / "error.log", logging.ERROR))

    if jobs_dir is None:
        return
    jobs = logging.getLogger(JOBS_LOGGER_NAME)
    for handler in list(jobs.handlers):
        jobs.removeHandler(handler)
        handler.close()
    jobs.addHandler(_make_file_handler(data_root / "logs" / jobs_dir / "jobs.log", logging.INFO))
    jobs.propagate = True  # 任务事件同时进入 app 全量日志
