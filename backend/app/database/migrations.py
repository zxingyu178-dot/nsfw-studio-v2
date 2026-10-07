"""极简迁移框架（Phase 0 规范 §十；Phase 0.1 收口失败恢复语义）。

设计：
- 迁移在代码中声明（单一事实源），按 ``migration_id`` 升序执行；
- ``applied_migration_ids()`` **只把 status='applied' 视为已完成**；
  status='failed' 的记录下次启动仍按"未完成"处理，不得静默跳过；
- 重试成功前先清除同一 migration_id 的历史 failed 记录，避免主键冲突；
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
    """返回已成功完成的迁移 ID 集合（只认 status='applied'）。"""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT migration_id FROM migration WHERE status = 'applied'")
        ).fetchall()
    return {row[0] for row in rows}


def _record(engine: Engine, migration: Migration, status: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT OR REPLACE INTO migration (migration_id, version, time, status) "
                "VALUES (:mid, :ver, :time, :status)"
            ),
            {
                "mid": migration.migration_id,
                "ver": migration.version,
                "time": datetime.now().isoformat(timespec="seconds"),
                "status": status,
            },
        )


def apply_pending_migrations(engine: Engine) -> list[Migration]:
    """应用全部待执行迁移，返回本次新应用的迁移列表。失败时记录 failed 并抛出。"""
    done = applied_migration_ids(engine)
    applied_now: list[Migration] = []

    for migration in sorted(MIGRATIONS, key=lambda item: item.migration_id):
        if migration.migration_id in done:
            continue
        try:
            with engine.begin() as conn:
                # 清除该迁移的历史 failed 记录，避免重试成功时主键冲突
                conn.execute(
                    text("DELETE FROM migration WHERE migration_id = :mid"),
                    {"mid": migration.migration_id},
                )
                for statement in migration.statements:
                    conn.execute(text(statement))
                conn.execute(
                    text(
                        "INSERT INTO migration (migration_id, version, time, status) "
                        "VALUES (:mid, :ver, :time, 'applied')"
                    ),
                    {
                        "mid": migration.migration_id,
                        "ver": migration.version,
                        "time": datetime.now().isoformat(timespec="seconds"),
                    },
                )
        except Exception:
            _record(engine, migration, "failed")
            raise
        applied_now.append(migration)

    return applied_now
