"""数据库安全备份（Phase 0.1 收口）。

使用 SQLite 官方 backup API 生成一致性快照：
- 在 WAL 模式下也安全（由源库页级复制，等效于对写入中的库做一致性快照）；
- 禁止直接复制正在写入的 DB 文件（可能得到损坏的副本）。

入口：``backup_database()``；命令行入口见 ``scripts/backup_db.py``。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


def backup_database(database_path: Path, backup_dir: Path, filename_prefix: str = "studio") -> Path:
    """把 ``database_path`` 安全备份到 ``backup_dir``，返回备份文件路径。

    文件名：{prefix}-YYYYmmdd-HHMMSS.db；同一秒内重复备份自动追加序号。
    """
    if not database_path.is_file():
        raise FileNotFoundError(f"源数据库不存在: {database_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / f"{filename_prefix}-{timestamp}.db"
    suffix = 1
    while dest.exists():
        dest = backup_dir / f"{filename_prefix}-{timestamp}-{suffix}.db"
        suffix += 1

    source = sqlite3.connect(str(database_path))
    try:
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)  # SQLite backup API：页级一致快照
        finally:
            target.close()
    finally:
        source.close()

    return dest
