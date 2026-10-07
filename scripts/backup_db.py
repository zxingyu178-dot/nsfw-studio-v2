"""NSFW Studio V2 - 数据库安全备份（SQLite backup API，WAL 下安全）。

用法（项目根目录）：
    .venv/Scripts/python scripts/backup_db.py                # 备份到 DataRoot/backups
    NSFW_STUDIO_DATA_ROOT="..." python scripts/backup_db.py  # 指定 DataRoot
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_settings  # noqa: E402
from app.database.backup import backup_database  # noqa: E402


def main() -> int:
    settings = load_settings()
    database_path = settings.storage.database_path
    backup_dir = settings.storage.data_root / "backups"
    dest = backup_database(database_path, backup_dir)
    print(f"源数据库: {database_path}")
    print(f"备份完成: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
