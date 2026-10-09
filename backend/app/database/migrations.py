"""极简迁移框架（Phase 0 规范 §十；Phase 0.1 收口失败恢复语义）。

设计：
- 迁移在代码中声明（单一事实源），按 ``migration_id`` 升序执行；
- ``applied_migration_ids()`` **只把 status='applied' 视为已完成**；
  status='failed' 的记录下次启动仍按"未完成"处理，不得静默跳过；
- 重试成功前先清除同一 migration_id 的历史 failed 记录，避免主键冲突；
- 失败时记录 ``failed`` 并抛出，阻止带伤启动；
- Phase 4：statement 可以是 SQL 字符串或 callable（数据回填等需要程序逻辑的迁移）；
- Phase 1 若复杂度上升，可平滑替换为 Alembic（见 docs/DATABASE_PLAN.md）。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine


@dataclass(frozen=True)
class Migration:
    migration_id: str
    version: str
    description: str
    # 每条 statement 为 SQL 字符串，或接收 Connection 的 callable（同一事务内执行）
    statements: tuple[str | Callable[[Connection], None], ...]


def _backfill_stage_status(job_status: str, item_statuses: list[str]) -> str:
    """旧 Job 状态 → Stage 状态映射（Phase 4 Task0）。

    - 终态 / RUNNING / INTERRUPTED 一一对应（RUNNING 由下次启动恢复转 INTERRUPTED）；
    - PAUSED：已开始过的 Stage 保持 RUNNING（与在线暂停语义一致），未开始为 QUEUED；
    - QUEUED / 未知：QUEUED。
    """
    if job_status in ("COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED", "RUNNING"):
        return job_status
    if job_status == "PAUSED":
        started = any(status != "QUEUED" for status in item_statuses)
        return "RUNNING" if started else "QUEUED"
    return "QUEUED"


def _backfill_pipeline_stages(conn: Connection) -> None:
    """0008：为已执行过 0007、但没有 Stage 的历史 Job 回填 Stage0 + StageItem（Phase 4 Task0）。

    规则（合同 Task 0）：
    - 只处理 ``jobs WHERE NOT EXISTS job_stages``；**不改变历史 Job 本身状态**；
    - Stage 身份优先继承 job 列（module_id/module_version/provider/binding_version/workflow_hash）；
    - StageItem 状态直接映射自 JobItem（旧 RUNNING 保留，由启动恢复流程转 INTERRUPTED）；
    - output_image_id = JobItem.image_id；input_image_id 保持 NULL（v0.3.x 无输入图片语义）；
    - total_count = requested_count，completed_count = 已完成数量。
    """
    from app.core.ids import JOB_STAGE, JOB_STAGE_ITEM, new_id

    jobs = conn.execute(text(
        "SELECT id, status, requested_count, module_id, module_version, provider, binding_version, "
        "workflow_hash, created_at, updated_at, finished_at FROM jobs "
        "WHERE NOT EXISTS (SELECT 1 FROM job_stages WHERE job_stages.job_id = jobs.id)"
    )).mappings().all()

    for job in jobs:
        items = conn.execute(text(
            "SELECT id, item_index, status, engine_job_id, progress, image_id, error_type, error_message, "
            "retry_count, created_at, started_at, finished_at, updated_at FROM job_items "
            "WHERE job_id = :job_id ORDER BY item_index"
        ), {"job_id": job["id"]}).mappings().all()

        completed_count = sum(1 for item in items if item["status"] == "COMPLETED")
        stage_status = _backfill_stage_status(
            str(job["status"]), [str(item["status"]) for item in items]
        )
        stage_id = new_id(JOB_STAGE)
        started_at = next((item["started_at"] for item in items if item["started_at"]), None)
        conn.execute(text(
            "INSERT INTO job_stages (id, job_id, stage_index, module_id, module_version, provider, "
            "binding_version, workflow_hash, status, total_count, completed_count, config_json, "
            "created_at, started_at, finished_at, updated_at) "
            "VALUES (:id, :job_id, 0, :module_id, :module_version, :provider, :binding_version, "
            ":workflow_hash, :status, :total_count, :completed_count, '{}', "
            ":created_at, :started_at, :finished_at, :updated_at)"
        ), {
            "id": stage_id,
            "job_id": job["id"],
            "module_id": job["module_id"] or "basic_generate",
            "module_version": job["module_version"] or "v1",
            "provider": job["provider"],
            "binding_version": job["binding_version"],
            "workflow_hash": job["workflow_hash"],
            "status": stage_status,
            "total_count": job["requested_count"],
            "completed_count": completed_count,
            "created_at": job["created_at"],
            "started_at": started_at,
            "finished_at": job["finished_at"],
            "updated_at": job["updated_at"],
        })
        for item in items:
            conn.execute(text(
                "INSERT INTO job_stage_items (id, job_stage_id, job_item_id, item_index, input_image_id, "
                "output_image_id, status, engine_job_id, progress, error_type, error_message, retry_count, "
                "created_at, started_at, finished_at, updated_at) "
                "VALUES (:id, :job_stage_id, :job_item_id, :item_index, NULL, :output_image_id, "
                ":status, :engine_job_id, :progress, :error_type, :error_message, :retry_count, "
                ":created_at, :started_at, :finished_at, :updated_at)"
            ), {
                "id": new_id(JOB_STAGE_ITEM),
                "job_stage_id": stage_id,
                "job_item_id": item["id"],
                "item_index": item["item_index"],
                "output_image_id": item["image_id"],
                "status": item["status"],
                "engine_job_id": item["engine_job_id"],
                "progress": item["progress"],
                "error_type": item["error_type"],
                "error_message": item["error_message"],
                "retry_count": item["retry_count"],
                "created_at": item["created_at"],
                "started_at": item["started_at"],
                "finished_at": item["finished_at"],
                "updated_at": item["updated_at"],
            })


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
    Migration(
        migration_id="0006_image",
        version="0.3.0",
        description="Phase 2C：images（图库正式资产；文件在 DataRoot/images/originals）",
        statements=(
            """
            CREATE TABLE images (
                id               TEXT PRIMARY KEY,
                job_id           TEXT REFERENCES jobs(id),
                job_item_id      TEXT REFERENCES job_items(id),
                parent_image_id  TEXT REFERENCES images(id),
                kind             TEXT NOT NULL CHECK (kind IN ('original', 'upscaled', 'processed')),
                file_path        TEXT NOT NULL,
                width            INTEGER NOT NULL CHECK (width > 0),
                height           INTEGER NOT NULL CHECK (height > 0),
                seed             INTEGER,
                review_status    TEXT NOT NULL DEFAULT 'UNREVIEWED'
                                 CHECK (review_status IN ('UNREVIEWED', 'KEPT', 'REJECTED')),
                favorite         INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)),
                source           TEXT NOT NULL,
                metadata_json    TEXT NOT NULL DEFAULT '{}',
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_images_job ON images(job_id)",
            "CREATE INDEX idx_images_review ON images(review_status)",
            "CREATE INDEX idx_images_created ON images(created_at)",
        ),
    ),
    Migration(
        migration_id="0007_pipeline_stage",
        version="0.4.0",
        description="Phase 3：job_stages / job_stage_items + jobs.job_kind（多阶段管线）",
        statements=(
            "ALTER TABLE jobs ADD COLUMN job_kind TEXT NOT NULL DEFAULT 'generate'",
            """
            CREATE TABLE job_stages (
                id               TEXT PRIMARY KEY,
                job_id           TEXT NOT NULL REFERENCES jobs(id),
                stage_index      INTEGER NOT NULL,
                module_id        TEXT NOT NULL,
                module_version   TEXT NOT NULL,
                provider         TEXT,
                binding_version  TEXT,
                workflow_hash    TEXT,
                status           TEXT NOT NULL DEFAULT 'QUEUED'
                                 CHECK (status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED','INTERRUPTED')),
                total_count      INTEGER NOT NULL DEFAULT 0,
                completed_count  INTEGER NOT NULL DEFAULT 0,
                config_json      TEXT NOT NULL DEFAULT '{}',
                created_at       TEXT NOT NULL,
                started_at       TEXT,
                finished_at      TEXT,
                updated_at       TEXT NOT NULL
            )
            """,
            "CREATE UNIQUE INDEX uq_job_stages_index ON job_stages(job_id, stage_index)",
            """
            CREATE TABLE job_stage_items (
                id               TEXT PRIMARY KEY,
                job_stage_id     TEXT NOT NULL REFERENCES job_stages(id),
                job_item_id      TEXT NOT NULL REFERENCES job_items(id),
                item_index       INTEGER NOT NULL,
                input_image_id   TEXT,
                output_image_id  TEXT,
                status           TEXT NOT NULL DEFAULT 'QUEUED'
                                 CHECK (status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED','INTERRUPTED')),
                engine_job_id    TEXT,
                progress         REAL,
                error_type       TEXT,
                error_message    TEXT,
                retry_count      INTEGER NOT NULL DEFAULT 0,
                created_at       TEXT NOT NULL,
                started_at       TEXT,
                finished_at      TEXT,
                updated_at       TEXT NOT NULL
            )
            """,
            "CREATE INDEX idx_stage_items_stage ON job_stage_items(job_stage_id)",
            "CREATE INDEX idx_stage_items_item ON job_stage_items(job_item_id)",
        ),
    ),
    Migration(
        migration_id="0008_pipeline_backfill",
        version="0.5.0",
        description="Phase 4：为已执行过 0007 但没有 Stage 的历史 Job 回填 Stage0/StageItem",
        statements=(
            _backfill_pipeline_stages,
        ),
    ),
    Migration(
        migration_id="0009_execution_fingerprint",
        version="0.5.0",
        description="Phase 4：jobs/job_stages.binding_hash + job_stage_items.seed（执行指纹完整化）",
        statements=(
            # Task 1：binding_hash 与 workflow_hash 并列，完整覆盖 workflow.json + binding.yaml
            "ALTER TABLE jobs ADD COLUMN binding_hash TEXT",
            "ALTER TABLE job_stages ADD COLUMN binding_hash TEXT",
            # Task 3：StageItem 自己的真实 Seed（uses_seed=false 的 Stage 为 NULL）
            "ALTER TABLE job_stage_items ADD COLUMN seed INTEGER",
            # 历史数据修正 1：回填 StageItem.seed（仅 basic_generate Stage——upscale Stage 不使用 seed，
            # 旧版写入 JobItem 的随机数从未被高清模型使用，禁止冒领）
            """
            UPDATE job_stage_items SET seed = (
                SELECT ji.seed FROM job_items ji WHERE ji.id = job_stage_items.job_item_id
            )
            WHERE seed IS NULL
              AND job_stage_id IN (SELECT id FROM job_stages WHERE module_id = 'basic_generate')
              AND EXISTS (
                SELECT 1 FROM job_items ji
                WHERE ji.id = job_stage_items.job_item_id AND ji.seed IS NOT NULL
              )
            """,
            # 历史数据修正 2：upscale Stage 输出的高清图不得携带"假 Seed"（从未被高清模型使用）
            """
            UPDATE images SET seed = NULL
            WHERE seed IS NOT NULL AND id IN (
                SELECT si.output_image_id FROM job_stage_items si
                JOIN job_stages st ON st.id = si.job_stage_id
                WHERE st.module_id = 'upscale' AND si.output_image_id IS NOT NULL
            )
            """,
            # 历史数据修正 3：upscale-only（process）Job 的 JobItem.seed 同样为假 Seed → 清空
            """
            UPDATE job_items SET seed = NULL
            WHERE seed IS NOT NULL
              AND job_id IN (SELECT DISTINCT job_id FROM job_stages WHERE module_id = 'upscale')
              AND job_id NOT IN (SELECT DISTINCT job_id FROM job_stages WHERE module_id = 'basic_generate')
            """,
        ),
    ),
    Migration(
        migration_id="0010_image_inputs",
        version="0.6.0",
        description=(
            "Phase 5：images.sha256/imported_filename（导入去重）+ "
            "recipe_versions.input_images_json（输入图快照）+ asset_reference_images（Face Asset 参考图关系表）"
        ),
        statements=(
            # 外部导入图片来源哈希（Task6：禁止只按文件名去重）
            "ALTER TABLE images ADD COLUMN sha256 TEXT",
            "ALTER TABLE images ADD COLUMN imported_filename TEXT",
            "CREATE INDEX idx_images_sha256 ON images(sha256)",
            # RecipeVersion 输入图快照（Task9：image_id + file hash + role；旧版本为空数组）
            "ALTER TABLE recipe_versions ADD COLUMN input_images_json TEXT NOT NULL DEFAULT '[]'",
            # Face Asset Reference Image 正式关系表（Task12/13：不再把复杂关系长期塞 JSON）
            """
            CREATE TABLE asset_reference_images (
                id               TEXT PRIMARY KEY,
                asset_version_id TEXT NOT NULL REFERENCES asset_versions(id),
                image_id         TEXT NOT NULL REFERENCES images(id),
                role             TEXT NOT NULL,
                sort_order       INTEGER NOT NULL DEFAULT 0,
                created_at       TEXT NOT NULL,
                UNIQUE (asset_version_id, role, sort_order)
            )
            """,
            "CREATE INDEX idx_asset_reference_images_version ON asset_reference_images(asset_version_id)",
            "CREATE INDEX idx_asset_reference_images_image ON asset_reference_images(image_id)",
        ),
    ),
    Migration(
        migration_id="0011_image_import_dedup_unique",
        version="0.7.0",
        description=(
            "Phase 5.1 Task9：images(sha256) 部分唯一索引（source='import'）兜底并发导入竞态"
        ),
        statements=(
            # 防御性去重：唯一索引创建前，把历史重复导入行的 sha256 置空
            # （保留最早一行；不改文件、不删数据——重复行的图片本体仍可正常使用）
            """
            UPDATE images SET sha256 = NULL
            WHERE source = 'import' AND sha256 IS NOT NULL
              AND rowid NOT IN (
                  SELECT MIN(rowid) FROM images
                  WHERE source = 'import' AND sha256 IS NOT NULL
                  GROUP BY sha256
              )
            """,
            # 部分唯一索引：只约束外部导入且非空 hash 的行（引擎生成图 sha256 可为 NULL）
            "CREATE UNIQUE INDEX uq_images_import_sha256 "
            "ON images(sha256) WHERE source = 'import' AND sha256 IS NOT NULL",
        ),
    ),
    Migration(
        migration_id="0012_stage_item_reuse_trace",
        version="0.9.0",
        description=(
            "Phase 7 Task0：job_stage_items.reused_from_stage_item_id"
            "（Stage-aware Resume 溯源：复用自父 Job 的哪个 StageItem）"
        ),
        statements=(
            "ALTER TABLE job_stage_items ADD COLUMN reused_from_stage_item_id TEXT",
        ),
    ),
    Migration(
        migration_id="0013_client_request_fingerprint",
        version="0.9.0",
        description=(
            "Phase 7 Task7：jobs.client_request_fingerprint"
            "（幂等键冲突判定：相同 key + 不同 payload → IDEMPOTENCY_KEY_CONFLICT）"
        ),
        statements=(
            "ALTER TABLE jobs ADD COLUMN client_request_fingerprint TEXT",
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
                    if callable(statement):
                        statement(conn)  # 数据回填等程序化迁移（同一事务）
                    else:
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
