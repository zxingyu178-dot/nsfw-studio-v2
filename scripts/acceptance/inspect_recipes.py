"""只读检查：真实 DataRoot 的 recipes / recipe_versions 摘要（验收辅助，Phase 7 Task1 迁移）。

用法：
    .venv/Scripts/python scripts/acceptance/inspect_recipes.py [数据库路径]
默认数据库：D:\\NSFW-Studio-Data\\database\\studio.db
"""
import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else r"D:\NSFW-Studio-Data\database\studio.db"
conn = sqlite3.connect(db_path)
print(f"db: {db_path}")
print("== recipes (last 5) ==")
for row in conn.execute(
    "select id, name, created_at from recipes order by created_at desc limit 5"
):
    print(row)
print("== recipe versions (last 5) ==")
for row in conn.execute(
    "select id, recipe_id, version_no, generation_settings_json, created_at "
    "from recipe_versions order by created_at desc limit 5"
):
    print(row)