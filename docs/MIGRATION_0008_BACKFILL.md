# MIGRATION_0008_BACKFILL — 历史 Job Stage 回填 + 执行指纹列（Phase 4 / v0.5.0）

> Task 0/1/3 的迁移说明：`0008_pipeline_backfill`（数据回填）+ `0009_execution_fingerprint`（列与历史修正）。
> **已发布的 0007_pipeline_stage 不做任何修改。**

## 1. 背景（为什么必须新增 0008）

v0.3.x（无 Stage 概念）的 Job 升级到 v0.4.x 时，`0007` 只建了表，**没有给历史 Job 回填 Stage**。
真实复现：v0.3.2 的 QUEUED Job 升级后 `job_stages = 0`，Worker 领取后 Job 直接 FAILED、原任务完全没有执行。
`0008_pipeline_backfill` 修复所有"已执行过 0007、但历史 Job 没有 Stage"的数据库。

## 2. 0008_pipeline_backfill

扫描 `jobs WHERE NOT EXISTS (SELECT 1 FROM job_stages WHERE job_id = jobs.id)`，
为每个旧 Job 创建一个 Stage 0（`stage_index = 0`）与对应 StageItem：

| 字段 | 规则 |
| --- | --- |
| Stage.module_id / module_version | 优先继承 `jobs.module_id / module_version`，缺失回落 `basic_generate / v1` |
| Stage.provider / binding_version / workflow_hash | 继承 Job 同名列 |
| Stage.total_count | `jobs.requested_count` |
| Stage.completed_count | 该 Job `COMPLETED` 的 JobItem 数量 |
| StageItem | 每个 JobItem 恰好一条；`item_index` 对齐 |
| StageItem.status | 直接映射自 JobItem.status（旧 RUNNING 保留，由下次启动恢复流程转 INTERRUPTED） |
| StageItem.output_image_id | `JobItem.image_id`（不丢失图片关系） |
| StageItem.engine_job_id / progress / error / retry_count / 各时间戳 | 从 JobItem 复制（保留恢复核对信息） |
| StageItem.input_image_id | NULL（v0.3.x 无输入图片语义） |
| **Job 本身状态** | **绝不修改** |

### Stage 状态映射

| 旧 Job 状态 | Stage 状态 |
| --- | --- |
| COMPLETED / FAILED / CANCELLED | 同值 |
| RUNNING | RUNNING（启动时恢复流程转 INTERRUPTED） |
| INTERRUPTED | INTERRUPTED |
| PAUSED | 已开始过（任一 Item 非 QUEUED）→ RUNNING；否则 QUEUED（与在线暂停语义一致） |
| QUEUED | QUEUED |

## 3. 0009_execution_fingerprint

```sql
ALTER TABLE jobs            ADD COLUMN binding_hash TEXT;   -- Task1 执行指纹
ALTER TABLE job_stages      ADD COLUMN binding_hash TEXT;
ALTER TABLE job_stage_items ADD COLUMN seed INTEGER;        -- Task3 真实 Seed
```

### 历史数据修正（同一迁移内）

1. **回填 StageItem.seed**：仅 `module_id = 'basic_generate'` 的 Stage——
   从 JobItem.seed 复制（upscale Stage 不使用 seed，禁止冒领）。
2. **清空高清图假 Seed**：upscale Stage 产出的 `Image.seed = NULL`
   （旧版写入的随机数从未被高清模型使用）。
3. **清空 process Job 的假 Seed**：upscale-only Job 的 `JobItem.seed = NULL`。

## 4. 兼容性

- 老 Job 的 `binding_hash = null` → 允许兼容执行（新 Job 必须记录）；
- 老 Job 的 `workflow_hash` 校验逻辑不变（不一致 → `WORKFLOW_HASH_MISMATCH`）；
- 迁移框架新增 callable statement 支持（`statements` 可为 SQL 或 `(conn) -> None`），
  0008 的回填逻辑在单一事务内执行，失败整体回滚。

## 5. 升级测试（强制，禁止只测"表存在"）

`tests/backend/test_phase4_backfill.py::test_v032_database_backfill_and_queued_job_still_runs`：

```
真实 v0.3.2 数据库（0001~0006）
├─ COMPLETED Job（含 image + seed）
├─ QUEUED Job
├─ PAUSED Job（1 完成 / 1 排队）
└─ INTERRUPTED Job（保留 engine_job_id）
↓ 0007 + 0008 + 0009
每个 Job 都有 1 个 Stage（身份继承 job 列）+ 对应 StageItem
历史状态与图片关系不丢失；StageItem.seed 正确回填
↓ 启动应用（Mock 引擎）
QUEUED Job 被同一 Worker 真实执行 → COMPLETED（证明回填语义可执行）
其他历史 Job 状态不被破坏
```