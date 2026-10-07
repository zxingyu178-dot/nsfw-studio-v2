"""极简迁移框架（Phase 0 规范 §十）。

设计：
- 迁移在代码中声明（单一事实源），按 ``migration_id`` 升序执行；
- 每次执行写入 ``migration`` 表（migration_id / version / time / status）；
- 失败时记录 ``failed`` 并抛出，阻止带伤启动；
- Phase 1 若复杂度上升，可平滑替换为 Alembic（见 docs/DATABASE_PLAN.md）。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class Migration:
    migration_id: str
    version: str
    description: str
    statements: tuple[str, ...]


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        migration_id="0001_initial_schema",
        version="0.1.0",
        description="创建 system_info 基础表",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS system_info (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                version      TEXT    NOT NULL,
                created_time TEXT    NOT NULL,
                updated_time TEXT    NOT NULL
            )
            """,
        ),
    ),
)


def applied_migration_ids(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT migration_id FROM migration")).fetchall()
    return {row[0] for row in rows}


def apply_pending_migrations(engine: Engine) -> list[Migration]:
    """应用全部待执行迁移，返回本次新应用的迁移列表。"""
    done = applied_migration_ids(engine)
    applied_now: list[Migration] = []

    for migration in sorted(MIGRATIONS, key=lambda item: item.migration_id):
        if migration.migration_id in done:
            continue
        try:
            with engine.begin() as conn:
                for statement in migration.statements:
                    conn.execute(text(statement))
                conn.execute(
                    text(
                        "INSERT INTO migration (migration_id, version, time, status) "
                        "VALUES (:mid, :ver, :time, :status)"
                    ),
                    {
                        "mid": migration.migration_id,
                        "ver": migration.version,
                        "time": datetime.now().isoformat(timespec="seconds"),
                        "status": "applied",
                    },
                )
        except Exception:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT OR REPLACE INTO migration (migration_id, version, time, status) "
                        "VALUES (:mid, :ver, :time, 'failed')"
                    ),
                    {
                        "mid": migration.migration_id,
                        "ver": migration.version,
                        "time": datetime.now().isoformat(timespec="seconds"),
                    },
                )
            raise
        applied_now.append(migration)

    return applied_now
