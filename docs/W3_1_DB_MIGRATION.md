# W3.1 Gate 0 — 两套 0021 数据库兼容报告

> 检查对象：真实 DataRoot `D:\NSFW-Studio-Data\database\studio.db`（**只读备份**）。
> 验证方式：SQLite backup API 生成副本 → 在副本执行 0021 守卫 + 0022 → 前后结构/计数对比。
> **未对正式数据库执行任何迁移**；生产迁移需在部署窗口备份后由启动流程执行。

## 1. 部署库实际状态

`migration` 表最新记录：

```
0020_review_session_end_reason   0.37.0   applied
0021_mobile_v2_events            0.38.0   applied   ← 参考分支迁移
```

主干 W3.0 迁移 `0021_mobile_event_log_mutations` **不在部署库**。

### 1.1 两套 0021 差异

| 对象 | main W3.0 `0021_mobile_event_log_mutations` | 参考分支 `0021_mobile_v2_events` |
| --- | --- | --- |
| `mobile_image_events` | `seq, event_id(UNIQUE), event_type, image_id, revision, payload_json, created_at` | `seq, image_id, event(VARCHAR UPSERT/REMOVE)` |
| 事件写入 | 业务服务显式写事件（同事务） | images AFTER INSERT/UPDATE/DELETE 触发器 |
| 历史图片 | 无回填 | 迁移时 `INSERT ... SELECT` 回填 |
| 幂等回执 | `mobile_mutation_receipts(device_id,operation,idempotency_key)` | `mobile_write_receipts(device_id,request_id,operation,fingerprint)` |
| 已读 | 无独立表（用 reviewed_at / session item seen） | `mobile_image_seen(device_id,image_id,seen)` |
| 游标身份 | 无独立表（`mr2_` base64 seq） | `mobile_feed_identity(epoch)` + HMAC 游标 |
| 迁移冲突 | 直接执行会在已存在 `mobile_image_events` 上建表失败 | 直接执行会向主干事件表写不存在的列 |

## 2. 迁移前后结构与计数（副本）

### 2.1 迁移前

| 对象 | 计数 | 结构要点 |
| --- | ---: | --- |
| `images` | 5383 | 不变 |
| `jobs` | 599 | 不变 |
| `prompts` / `prompt_versions` | 292 / 292 | 不变 |
| `prompt_evaluations` | 1 | 不变 |
| `mobile_review_devices` | 2 | 不变 |
| `mobile_review_sessions` / items | 5 / 5389 | 不变 |
| `mobile_image_events` | 5439（max seq 5439） | `seq,image_id,event` |
| `mobile_write_receipts` | 54 | 旧分支回执 |
| `mobile_image_seen` | 24 | 旧分支已读 |
| `mobile_feed_identity` | 1 | epoch 保留 |
| images 触发器 | 3 个 | INSERT/UPDATE/DELETE 写旧事件表 |

### 2.2 迁移后

| 对象 | 计数 | 结构要点 |
| --- | ---: | --- |
| `images` / `jobs` / `prompts` / `prompt_versions` / `prompt_evaluations` | 5383 / 599 / 292 / 292 / 1 | 全部保留 |
| `mobile_review_devices` | 2 | 已配对设备保留 |
| `mobile_review_sessions` / items | 5 / 5389 | 冻结会话保留 |
| `mobile_image_events` | **5439** | 保 seq；新增 `event_id/event_type/revision/payload_json/created_at`；保留旧 `event` 审计列 |
| `mobile_mutation_receipts` | **54** | 旧 `mobile_write_receipts` 全量合并，`payload_hash=legacy_fp:...` |
| `mobile_write_receipts` | 54 | 原表保留（不删除历史） |
| `mobile_image_seen` | 24 | 保留并供 V2 summary 使用 |
| `mobile_feed_identity` | 1 | 保留（当前主干不依赖） |
| images 触发器 | **0** | 删除，唯一事件机制 = 业务服务 |
| 事件 `revision` 空值 | 0 | 全部为 seq 十进制字符串 |

事件类型分布（迁移后）：`IMAGE_CREATED=5384`、`IMAGE_METADATA_UPDATED=54`、
`IMAGE_REMOVED=1`；历史图片均进入首次同步。

再次执行 `init_database` 返回 `[]`，迁移幂等。

## 3. 兼容方案

### 3.1 `0021_mobile_event_log_mutations` 改为 callable 守卫

- 若 `mobile_image_events` **不存在**：创建主干表 + 索引；
- 若已是主干结构：只补索引；
- 若检测到旧分支 `(seq,image_id,event)`：**不改写**，只创建 `mobile_mutation_receipts`，
  并记录 0021 主干 ID 为 applied；结构转换交给 0022。

### 3.2 新增 `0022_mobile_v2_compat`（幂等 callable）

1. 删除 `mobile_image_insert/update/delete` 三个触发器；
2. 旧事件表原位 `ADD COLUMN`（event_id/event_type/revision/payload_json/created_at），
   保留 `seq` 与原 `event`；补唯一索引 `uq_mobile_image_events_event_id`；
3. 为没有任何事件的历史图片补首事件（`IMAGE_CREATED` / `IMAGE_IMPORTED`），
   写入后回填 `revision=seq`；
4. `CREATE TABLE IF NOT EXISTS mobile_image_seen`；
5. `mobile_write_receipts` → `mobile_mutation_receipts`：
   `decision:* → image_decision`、`evaluation:* → prompt_evaluation`，
   `request_id → idempotency_key`，`fingerprint → legacy_fp:<fp>`，保留 `result_json`；
6. 不删除任何图片 / Job / Prompt / PromptVersion / PromptEvaluation / 设备。

### 3.3 受限环境修正

迁移事务开始即 `PRAGMA temp_store=MEMORY`，并在迁移框架写事务入口统一设置，
避免 SQLite 在 DDL/复杂排序时申请不可用临时文件导致
`unable to open database file`（在部署副本上已复现并验证修复）。

## 4. 验证记录

| 场景 | 结果 |
| --- | --- |
| 部署副本（旧分支 0021）升级 | 0021 守卫 + 0022 applied；数据计数如上；二次执行无迁移 |
| 主干 0021 库（缺历史事件）升级 | 0022 为历史图片补事件，revision 非空 |
| 旧分支回执重放 | 旧指纹算法复核成功；不同载荷 → `IDEMPOTENCY_CONFLICT` |
| 正式 DataRoot | **未执行迁移**（仅只读备份验证） |

测试：`tests/backend/test_mobile_v2_migration.py`（3 例）。
