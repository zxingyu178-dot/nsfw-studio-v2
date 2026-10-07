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
    Migration(
        migration_id="0002_prompt",
        version="0.2.0",
        description="Phase 1：prompts / prompt_versions（版本不可变，软删除）",
        statements=(
            """
            CREATE TABLE prompts (
                id                 TEXT PRIMARY KEY,
                name               TEXT    NOT NULL,
                current_version_id TEXT,
                favorite           INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)),
                archived           INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
                created_at         TEXT    NOT NULL,
                updated_at         TEXT    NOT NULL
            )
            """,
            """
            CREATE TABLE prompt_versions (
                id               TEXT PRIMARY KEY,
                prompt_id        TEXT NOT NULL REFERENCES prompts(id),
                version_no       INTEGER NOT NULL,
                mode             TEXT NOT NULL CHECK (mode IN ('structured', 'full')),
                positive_prompt  TEXT NOT NULL DEFAULT '',
                negative_prompt  TEXT NOT NULL DEFAULT '',
                structured_json  TEXT NOT NULL DEFAULT '{}',
                created_at       TEXT NOT NULL,
                UNIQUE (prompt_id, version_no)
            )
            """,
            "CREATE INDEX idx_prompt_versions_prompt ON prompt_versions(prompt_id)",
            "CREATE INDEX idx_prompts_archived ON prompts(archived)",
        ),
    ),
    Migration(
        migration_id="0003_asset",
        version="0.2.0",
        description="Phase 1：assets / asset_versions（四类素材，版本不可变，软删除）",
        statements=(
            """
            CREATE TABLE assets (
                id                 TEXT PRIMARY KEY,
                type               TEXT NOT NULL CHECK (type IN ('face', 'clothing', 'pose', 'scene')),
                name               TEXT NOT NULL,
                current_version_id TEXT,
                favorite           INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)),
                archived           INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
                source_image_id    TEXT,
                created_at         TEXT NOT NULL,
                updated_at         TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE asset_versions (
                id                    TEXT PRIMARY KEY,
                asset_id              TEXT NOT NULL REFERENCES assets(id),
                version_no            INTEGER NOT NULL,
                prompt_text           TEXT NOT NULL DEFAULT '',
                notes                 TEXT NOT NULL DEFAULT '',
                preview_path          TEXT,
                reference_images_json TEXT NOT NULL DEFAULT '[]',
                tags_json             TEXT NOT NULL DEFAULT '[]',
                created_at            TEXT NOT NULL,
                UNIQUE (asset_id, version_no)
            )
            """,
            "CREATE INDEX idx_asset_versions_asset ON asset_versions(asset_id)",
            "CREATE INDEX idx_assets_type ON assets(type)",
            "CREATE INDEX idx_assets_archived ON assets(archived)",
        ),
    ),
    Migration(
        migration_id="0004_recipe",
        version="0.2.0",
        description="Phase 1：recipes / recipe_versions / recipe_asset_snapshots（工作台快照）",
        statements=(
            """
            CREATE TABLE recipes (
                id                 TEXT PRIMARY KEY,
                name               TEXT NOT NULL,
                current_version_id TEXT,
                favorite           INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)),
                archived           INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
                cover_image_id     TEXT,
                created_at         TEXT NOT NULL,
                updated_at         TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE recipe_versions (
                id                        TEXT PRIMARY KEY,
                recipe_id                 TEXT NOT NULL REFERENCES recipes(id),
                version_no                INTEGER NOT NULL,
                prompt_mode               TEXT NOT NULL CHECK (prompt_mode IN ('structured', 'full')),
                positive_prompt_snapshot  TEXT NOT NULL DEFAULT '',
                negative_prompt_snapshot  TEXT NOT NULL DEFAULT '',
                structured_prompt_snapshot TEXT NOT NULL DEFAULT '{}',
                source_prompt_id          TEXT REFERENCES prompts(id),
                source_prompt_version_id  TEXT REFERENCES prompt_versions(id),
                generation_settings_json  TEXT NOT NULL,
                workflow_snapshot_json    TEXT NOT NULL DEFAULT '{"modules":[]}',
                default_count             INTEGER NOT NULL DEFAULT 1 CHECK (default_count >= 1),
                created_at                TEXT NOT NULL,
                UNIQUE (recipe_id, version_no)
            )
            """,
            """
            CREATE TABLE recipe_asset_snapshots (
                id                    TEXT PRIMARY KEY,
                recipe_version_id     TEXT NOT NULL REFERENCES recipe_versions(id),
                slot                  TEXT NOT NULL CHECK (slot IN ('face', 'clothing', 'pose', 'scene')),
                asset_id              TEXT NOT NULL REFERENCES assets(id),
                asset_version_id      TEXT NOT NULL REFERENCES asset_versions(id),
                asset_name_snapshot   TEXT NOT NULL,
                prompt_snapshot       TEXT NOT NULL DEFAULT '',
                preview_path_snapshot TEXT,
                created_at            TEXT NOT NULL,
                UNIQUE (recipe_version_id, slot)
            )
            """,
            "CREATE INDEX idx_recipe_versions_recipe ON recipe_versions(recipe_id)",
            "CREATE INDEX idx_recipe_asset_snapshots_version ON recipe_asset_snapshots(recipe_version_id)",
            "CREATE INDEX idx_recipes_archived ON recipes(archived)",
        ),
    ),
    Migration(
        migration_id="0005_job",
        version="0.3.0",
        description="Phase 2A：jobs / job_items / job_events（单队列执行核心）",
        statements=(
            """
            CREATE TABLE jobs (
                id                         TEXT PRIMARY KEY,
                source                     TEXT NOT NULL CHECK (source IN ('web', 'resume', 'agent', 'doubao')),
                client_request_id          TEXT,
                status                     TEXT NOT NULL CHECK (status IN
                    ('QUEUED', 'RUNNING', 'PAUSED', 'INTERRUPTED', 'COMPLETED', 'FAILED', 'CANCELLED')),
                prompt_mode                TEXT NOT NULL CHECK (prompt_mode IN ('structured', 'full')),
                positive_prompt_snapshot   TEXT NOT NULL DEFAULT '',
                negative_prompt_snapshot   TEXT NOT NULL DEFAULT '',
                structured_prompt_snapshot TEXT NOT NULL DEFAULT '{}',
                workbench_snapshot_json    TEXT NOT NULL,
                generation_settings_json   TEXT NOT NULL,
                workflow_snapshot_json     TEXT NOT NULL DEFAULT '{"modules":[]}',
                module_id                  TEXT,
                module_version             TEXT,
                provider                   TEXT,
                binding_version            TEXT,
                workflow_hash              TEXT,
                requested_count            INTEGER NOT NULL CHECK (requested_count >= 1),
                completed_count            INTEGER NOT NULL DEFAULT 0,
                queue_position             INTEGER,
                priority                   INTEGER NOT NULL DEFAULT 0 CHECK (priority IN (0, 1)),
                resume_of_job_id           TEXT REFERENCES jobs(id),
                pause_requested            INTEGER NOT NULL DEFAULT 0 CHECK (pause_requested IN (0, 1)),
                cancel_requested           INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
                error_type                 TEXT,
                error_message              TEXT,
                created_at                 TEXT NOT NULL,
                started_at                 TEXT,
                finished_at                TEXT,
                updated_at                 TEXT NOT NULL
            )
            """,
            "CREATE UNIQUE INDEX uq_jobs_client_request ON jobs(source, client_request_id) "
            "WHERE client_request_id IS NOT NULL",
            "CREATE INDEX idx_jobs_status ON jobs(status)",
            """
            CREATE TABLE job_items (
                id            TEXT PRIMARY KEY,
                job_id        TEXT NOT NULL REFERENCES jobs(id),
                item_index    INTEGER NOT NULL,
                status        TEXT NOT NULL CHECK (status IN
                    ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', 'INTERRUPTED')),
                seed          INTEGER,
                engine_job_id TEXT,
                current_stage TEXT,
                progress      REAL,
                image_id      TEXT,
                error_type    TEXT,
                error_message TEXT,
                retry_count   INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT NOT NULL,
                started_at    TEXT,
                finished_at   TEXT,
                updated_at    TEXT NOT NULL,
                UNIQUE (job_id, item_index)
            )
            """,
            "CREATE INDEX idx_job_items_job ON job_items(job_id)",
            "CREATE INDEX idx_job_items_status ON job_items(status)",
            """
            CREATE TABLE job_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id       TEXT NOT NULL REFERENCES jobs(id),
                job_item_id  TEXT,
                event_type   TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at   TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_job_events_job ON job_events(job_id)",
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
