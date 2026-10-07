"""NSFW Studio V2 - 仅初始化 DataRoot 与数据库（不启动服务）。

用法（项目根目录）：
    python scripts/init_dataroot.py
    NSFW_STUDIO_DATA_ROOT="D:/tmp/x" python scripts/init_dataroot.py
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_settings  # noqa: E402
from app.services.system_service import bootstrap  # noqa: E402


def main() -> int:
    settings = load_settings()
    report = bootstrap(settings)
    print(f"DataRoot: {report.data_root}")
    print(f"数据库:   {report.database_path}")
    print(f"新建目录: {len(report.created_dirs)} 个")
    print(f"迁移:     {', '.join(report.applied_migrations) or '（无新迁移）'}")
    print("初始化完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
