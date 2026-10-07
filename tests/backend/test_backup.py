"""数据库安全备份（SQLite backup API；Phase 0.1）。"""
from __future__ import annotations

import sqlite3

from app.database.backup import backup_database
from app.services.system_service import bootstrap


def test_backup_creates_consistent_snapshot(settings):
    bootstrap(settings)

    backup_dir = settings.storage.data_root / "backups"
    dest = backup_database(settings.storage.database_path, backup_dir)

    assert dest.is_file() and dest.parent == backup_dir
    # 备份必须是有效且一致的数据库（能打开并读到 system_info）
    with sqlite3.connect(str(dest)) as conn:
        version = conn.execute("SELECT version FROM system_info").fetchall()
    assert version and version[0][0] == settings.app.version


def test_backup_refuses_missing_database(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        backup_database(tmp_path / "missing.db", tmp_path / "backups")
