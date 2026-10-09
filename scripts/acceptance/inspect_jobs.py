"""只读检查：真实 DataRoot 数据库最近任务与活动任务（验收辅助，Phase 7 Task1 迁移）。

用法：
    .venv/Scripts/python scripts/acceptance/inspect_jobs.py [数据库路径]
默认数据库：D:\\NSFW-Studio-Data\\database\\studio.db
"""
import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else r"D:\NSFW-Studio-Data\database\studio.db"
conn = sqlite3.connect(db_path)
print(f"db: {db_path}")
print("== recent jobs ==")
for row in conn.execute(
    "select id, status, job_kind, module_id, created_at from jobs order by created_at desc limit 12"
):
    print(row)
print("== non-terminal jobs ==")
for row in conn.execute(
    "select id, status, job_kind, created_at from jobs where status in ('QUEUED','RUNNING','PAUSED','INTERRUPTED')"
):
    print(row)