# DATABASE_PLAN — 数据库现状与规划

> 更新：2026-10-07（Phase 0）

## 1. 现状

- 引擎：SQLite，运行库位于 `{data_root}/database/studio.db`（默认 `D:/NSFW-Studio-Data/database/studio.db`）。
- ORM：SQLAlchemy 2.x（`app/database/base.py` 提供 `Base` 与引擎工厂）。
- 迁移：自研极简框架（`app/database/migrations.py`），迁移在代码中声明（单一事实源），
  执行记录写入 `migration` 表，失败记 `failed` 并中断启动。

### 当前表

**migration**（Phase 0 规范 §十）

| 列 | 类型 | 说明 |
| --- | --- | --- |
| migration_id | TEXT PK | 如 `0001_initial_schema` |
| version | TEXT | 迁移后 schema 版本 |
| time | TEXT (ISO) | 执行时间 |
| status | TEXT | applied / failed |

**system_info**（Phase 0 规范 §十）

| 列 | 类型 | 说明 |
| --- | --- | --- |
| id | INTEGER PK | 自增 |
| version | TEXT | 应用版本（首启写入 0.1.0） |
| created_time | TEXT (ISO) | |
| updated_time | TEXT (ISO) | onupdate 自动刷新 |

## 2. Phase 1 规划（数据模型设计阶段细化）

| 表 | 用途 | 关键字段（草案） |
| --- | --- | --- |
| job | 生成任务 | id, type, status, recipe_id, params_json, created_at … |
| job_item | 任务子项（批量） | id, job_id, status, image_id, error … |
| prompt | 提示词 | id, name, positive, negative, tags_json … |
| recipe | 配方（提示词组合模板） | id, name, prompt_ids_json, workflow_name, default_params_json … |
| asset | 素材（face/clothing/pose/scene） | id, category, file_path, thumb_path, tags_json … |
| image | 生成图片资产 | id, job_item_id, path, width, height, hash, meta_json … |

设计原则：所有表带 `created_time`；图片/素材表存**相对 DataRoot 的路径**，不存绝对路径；
JSON 字段存结构化扩展参数，为 WorkflowModule 留自由度。

## 3. 迁移策略

- Phase 1 继续用内置框架：每个迁移一个 `Migration(migration_id, version, description, statements)`，只增不改。
- 若出现需要交互/回滚的复杂迁移，再评估引入 Alembic（届时保留 `migration` 表做兼容视图）。
- 禁止手改 `studio.db`；结构变更必须走迁移。
