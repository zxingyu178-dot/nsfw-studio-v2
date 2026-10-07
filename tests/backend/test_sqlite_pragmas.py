"""SQLite 工程化收口：WAL / busy_timeout / foreign_keys（Phase 0.1）。"""
from __future__ import annotations

from sqlalchemy import text

from app.database.base import SQLITE_BUSY_TIMEOUT_MS, make_engine


def test_pragmas_applied_on_every_connection(settings):
    engine = make_engine(settings.storage.database_path)
    try:
        with engine.connect() as conn:
            foreign_keys = conn.execute(text("PRAGMA foreign_keys")).scalar()
            journal_mode = conn.execute(text("PRAGMA journal_mode")).scalar()
            busy_timeout = conn.execute(text("PRAGMA busy_timeout")).scalar()
        assert foreign_keys == 1, "foreign_keys 必须开启"
        assert journal_mode == "wal", "必须启用 WAL"
        assert busy_timeout == SQLITE_BUSY_TIMEOUT_MS
        # 第二个连接同样生效（listener 挂在每个 connect 上）
        with engine.connect() as conn2:
            assert conn2.execute(text("PRAGMA foreign_keys")).scalar() == 1
    finally:
        engine.dispose()
