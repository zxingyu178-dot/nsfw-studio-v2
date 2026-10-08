# DATABASE_PLAN — 数据库现状与规划

> 更新：2026-10-08（Phase 5，v0.6.0）。完整模型见 **docs/DATA_MODEL_V1.md**（权威文档）。

## 1. 现状

- 引擎：SQLite，运行库位于 `{data_root}/database/studio.db`（DataRoot 由配置分层决定：
  env > config.local.yaml（本机，gitignore）> config.yaml（公共模板）> `%USERPROFILE%/NSFW-Studio-Data`）。
- ORM：SQLAlchemy 2.x（`app/database/base.py` 提供 `Base` 与引擎工厂）。
- 连接规范（`make_engine()` 对每个连接生效）：`journal_mode=WAL`、`busy_timeout=5000`、`foreign_keys=ON`。
- 迁移：自研极简框架（`app/database/migrations.py`），迁移在代码中声明（单一事实源）。
- 备份：`app/database/backup.py` 使用 **SQLite backup API** 生成一致性快照（WAL 下安全），
  禁止直接复制写入中的 DB 文件；命令行入口 `scripts/backup_db.py`，输出到 `{data_root}/backups/`。

### 迁移清单

| migration_id | 版本 | 内容 |
| --- | --- | --- |
| 0001_initial_schema | 0.1.0 | system_info |
| 0002_prompt | 0.2.0 | prompts / prompt_versions |
| 0003_asset | 0.2.0 | assets / asset_versions |
| 0004_recipe | 0.2.0 | recipes / recipe_versions / recipe_asset_snapshots |
| 0005_job | 0.3.0 | jobs / job_items / job_events（Phase 2A） |
| 0006_image | 0.3.0 | images（Phase 2C；文件在 DataRoot/images/originals） |
| 0007_pipeline_stage | 0.4.0 | jobs.job_kind + job_stages / job_stage_items（Phase 3 多阶段管线） |
| 0008_pipeline_backfill | 0.5.0 | 历史 Job 回填 Stage0/StageItem（Phase 4 Task0，数据迁移，见 MIGRATION_0008_BACKFILL.md） |
| 0009_execution_fingerprint | 0.5.0 | jobs/job_stages.binding_hash + job_stage_items.seed + 历史假 Seed 修正（Phase 4 Task1/3） |
| 0010_image_inputs | 0.6.0 | images.sha256/imported_filename（+idx_images_sha256）+ recipe_versions.input_images_json + asset_reference_images 关系表（Phase 5） |

约束：FK 全局开启；`UNIQUE(parent_id, version_no)` ×3；`UNIQUE(recipe_version_id, slot)`；
`type / mode / slot / favorite / default_count` 均有 CHECK；
`jobs` 有 `UNIQUE(source, client_request_id)`（幂等）与 status CHECK；
`images` 有 `kind / review_status` CHECK；
`job_stages` 有 `UNIQUE(job_id, stage_index)` 与 status CHECK（QUEUED/RUNNING/COMPLETED/FAILED/CANCELLED/INTERRUPTED）；
`asset_reference_images` 有 `UNIQUE(asset_version_id, role, sort_order)`（Phase 5 §十三：参考图关系表，
不再把复杂关系长期塞 JSON）；
升级路径测试覆盖 v0.1.2 → 0.2.0 → 0.3.0 → 0.4.0 → 0.5.0 → 0.6.0，
并含**真实 v0.3.2 库升级**（四种状态 Job 的 Stage 回填 + QUEUED Job 升级后可执行，
见 tests/backend/test_phase4_backfill.py）。

### migration 状态机（Phase 0.1 修正）

- `applied_migration_ids()` **只把 status='applied' 视为已完成**；
- status='failed' 的迁移下次启动仍按未完成处理（重新尝试，不静默跳过）；
- 重试前先删除同一 migration_id 的 failed 记录，避免主键冲突；
- 执行失败 → 记录 failed → 抛出阻止带伤启动。

### 当前表

**migration**（Phase 0 规范 §十）

| 列 | 类型 | 说明 |
| --- | --- | --- |
| migration_id | TEXT PK | 如 `0001_initial_schema` |
| version | TEXT | 迁移后 schema 版本 |
| time | TEXT (ISO) | 执行时间 |
| status | TEXT | applied / failed（仅 applied 视为完成） |

**system_info**（Phase 0 规范 §十；Phase 0.1 明确语义）

| 列 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | 自增 |
| version | TEXT | **当前应用版本**（不是首次创建版本）：每次启动与 configs/app.yaml 的 version 对齐，不一致则更新（updated_time 自动刷新） |
| created_time | TEXT (ISO) | 首次写入时间 |
| updated_time | TEXT (ISO) | 最近一次版本更新时间 |

## 2. Phase 2 新增表（已实现）

| 表 | 用途 | 关键字段 |
| --- | --- | --- |
| jobs | 生成任务 | id, source, client_request_id, status, prompt 快照, workbench_snapshot_json, module/provider/binding/workflow_hash/binding_hash, requested/completed_count, queue_position, priority, resume_of_job_id, pause/cancel_requested |
| job_items | 每张输出 | id, job_id, item_index, status, seed, engine_job_id, current_stage, progress, image_id, error_type/message, retry_count |
| job_events | 追加型审计 | id, job_id, job_item_id, event_type, payload_json, created_at |
| images | 图库正式资产 | id, job_id, job_item_id, parent_image_id, kind, file_path, width/height, seed, review_status, favorite, source, metadata_json |
| job_stages | 多阶段管线阶段 | id, job_id, stage_index, module/version/provider/binding/workflow_hash/binding_hash, status, total/completed_count, config_json |
| job_stage_items | Stage 执行记录 | id, job_stage_id, job_item_id, item_index, input/output_image_id, seed, status, engine_job_id, progress, error/retry |

设计原则：所有表带 `created_at`；图片/素材表存**相对 DataRoot 的路径**，不存绝对路径；
JSON 字段存结构化扩展参数，为 WorkflowModule 留自由度。
Job 状态机 / 队列 / 恢复语义见 docs/JOB_STATE_MACHINE.md、QUEUE_SPEC.md、RECOVERY_SPEC.md。

## 3. 迁移策略

- Phase 1 继续用内置框架：每个迁移一个 `Migration(migration_id, version, description, statements)`，只增不改；
  Phase 4 起 `statements` 支持 callable（`(conn) -> None`，如 0008 的数据回填），同一事务内执行、失败整体回滚。
- 若出现需要交互/回滚的复杂迁移，再评估引入 Alembic（届时保留 `migration` 表做兼容视图）。
- 禁止手改 `studio.db`；结构变更必须走迁移。
