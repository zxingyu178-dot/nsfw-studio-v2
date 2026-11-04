# W4.1 Gate 0 — 数据库盘点报告

> 数据库：`D:\NSFW-Studio-Data\database\studio.db` · 大小：123,330,560 bytes
> 模式：只读（`file:...?mode=ro`）· 日期：2026-11-04 · 基线提交：`9904e12`
> 快照：`D:\NSFW-Studio-Data\backups\studio-20261104-103427.db`

---

## 1. 表清单与行数（27 张业务表）

| 表 | 行数 | 用途 | W4.1 归属 |
|---|---:|---|---|
| `images` | 7,733 | 图片资产主表 | Image Asset Center |
| `image_variants` | 10,613 | thumbnail / preview rendition | Image Asset Center（缓存） |
| `prompts` | 294 | 提示词主表 | Prompt Center |
| `prompt_versions` | 294 | 不可变提示词版本 | Prompt Center |
| `prompt_evaluations` | 1 | 评分 | Prompt Center |
| `assets` | 4 | 素材（face/clothing/pose/scene） | 既有素材体系，不并入图片资产 |
| `asset_versions` | 4 | 素材版本 | 同上 |
| `asset_reference_images` | 0 | 素材参考图关系 | 同上 |
| `jobs` | 946 | 生成任务 | Generation Provenance |
| `job_items` | 6,720 | 每次生成项与 Seed | Generation Provenance |
| `job_stages` | 954 | 执行阶段与绑定身份 | Generation Provenance |
| `job_stage_items` | 6,735 | 阶段项输入/输出/Seed | Generation Provenance |
| `job_events` | 328,958 | 任务事件日志 | 运行历史，保留 |
| `recipes` | 3 | 工作台快照 | 既有体系，不重建 |
| `recipe_versions` | 3 | Recipe 版本 | 同上 |
| `recipe_asset_snapshots` | 1 | Recipe 素材快照 | 同上 |
| `mobile_review_devices` | 3 | 手机配对设备 | MediaReview V2（合同冻结） |
| `mobile_review_pairing_codes` | 3 | 配对码 | 同上 |
| `mobile_review_sessions` | 5 | 冻结审核会话 | 同上 |
| `mobile_review_session_items` | 5,389 | 会话队列项 | 同上 |
| `mobile_image_events` | 8,006 | 图片事件增量日志 | 同上（W4.1 0023 兼容目标） |
| `mobile_image_seen` | 24 | 设备已读 | 同上 |
| `mobile_mutation_receipts` | 54 | 幂等回执 | 同上 |
| `mobile_write_receipts` | 54 | 旧分支回执（legacy） | 只保留，不删除 |
| `mobile_feed_identity` | 1 | 同步 epoch | 同上 |
| `migration` | 23 | 迁移执行记录 | 迁移审计 |
| `system_info` | 1 | 系统版本 | 系统 |

---

## 2. 核心表结构

### 2.1 `images`

```text
id TEXT PK
job_id TEXT NULL → jobs.id
job_item_id TEXT NULL → job_items.id
parent_image_id TEXT NULL → images.id
kind TEXT NOT NULL              -- original / upscaled / processed
file_path TEXT NOT NULL         -- DataRoot 相对路径（= storage_key）
width INTEGER NOT NULL
height INTEGER NOT NULL
seed INTEGER NULL
review_status TEXT NOT NULL     -- UNREVIEWED / KEPT / REJECTED（旧列）
favorite INTEGER NOT NULL
source TEXT NOT NULL            -- comfyui / mock / import / engine
metadata_json TEXT NOT NULL     -- 含 v1_output / module_id 等历史信息
created_at / updated_at TEXT
sha256 TEXT NULL                -- 只有导入图有值
imported_filename TEXT NULL
status TEXT NOT NULL            -- NEW / KEEP / REJECT / ARCHIVED（新列）
reviewed_at TEXT NULL
review_note TEXT NOT NULL
```

索引：`idx_images_job`、`idx_images_review`、`idx_images_created`、`idx_images_sha256`、
`uq_images_import_sha256`（`source='import'` 且 `sha256` 非空时唯一）、`idx_images_new_status`。

**W4.1 判断：** 现有 `images` 表可以承载 Image Asset Center；
`kind` 即 `asset_type`，`file_path` 即 `storage_key`，`parent_image_id` 即 `parent_asset_id`。
`mime_type / file_size` 存入 `metadata_json`，不新增重复业务表；`prompt_id / workflow_id /
model_snapshot` 通过 Job 关系投影。

### 2.2 `image_variants`

```text
id TEXT PK
image_id TEXT NOT NULL → images.id
variant_type TEXT NOT NULL  -- thumbnail / preview / upscaled / processed（CHECK）
path TEXT NOT NULL          -- DataRoot 相对路径
width / height INTEGER NULL
format TEXT NULL
created_at TEXT NOT NULL
```

索引：`idx_image_variants_image`、`uq_image_variants_thumbnail`（每图至多一个 thumbnail）。

实际数据只有 `thumbnail` 7,695 与 `preview` 2,918；无 `upscaled` / `processed` 变体记录。

### 2.3 `prompts` / `prompt_versions`

```text
prompts: id PK, name, current_version_id, preview_image_id, favorite, archived,
         status（keep/candidate/eliminated）, status_reason, created_at, updated_at
prompt_versions: id PK, prompt_id FK, version_no, mode(structured|full),
                 positive_prompt, negative_prompt, structured_json, created_at
                 UNIQUE(prompt_id, version_no)
```

- 294 条 Prompt 全部有 1 个版本（`version_no=1`）；没有多版本记录；
- `structured_json` 字段：`style/face/clothing/pose/scene/composition/lighting/extra`；
  98 条带 `_v1_migration` 标记；
- 无 `tags` 独立列/表：标签目前由结构化字段与调用方派生，W4.1 以 Manifest 标准定义，不新建重复标签表。

### 2.4 `jobs`

```text
id TEXT PK
source TEXT NOT NULL
status TEXT NOT NULL
prompt_mode TEXT NOT NULL
positive_prompt_snapshot / negative_prompt_snapshot / structured_prompt_snapshot TEXT
workbench_snapshot_json TEXT          -- 含 source_prompt_id / source_prompt_version_id / 输入图
generation_settings_json TEXT
workflow_snapshot_json TEXT
module_id / module_version / provider / binding_version TEXT NULL
workflow_hash TEXT NULL
binding_hash TEXT NULL
requested_count / completed_count / priority ...
job_kind TEXT NOT NULL
client_request_fingerprint TEXT NULL
created_at / started_at / finished_at / updated_at
```

946 条 Job 的 `workflow_hash` 与 `binding_hash` 均非空。

### 2.5 `mobile_image_events`（0023 目标）

当前生产库结构（已由 W4.0 一次性修复）：

```text
seq INTEGER PK AUTOINCREMENT
event_id TEXT NOT NULL UNIQUE
event_type TEXT NOT NULL
image_id TEXT NULL
revision TEXT NULL
payload_json TEXT NOT NULL DEFAULT '{}'
created_at TEXT NOT NULL
```

索引：`uq_mobile_image_events_event_id`、`idx_mobile_image_events_type`、`idx_mobile_image_events_image`。
数据：`IMAGE_CREATED` 7,735 / `IMAGE_METADATA_UPDATED` 269 / `IMAGE_REMOVED` 2。

**风险：** 旧分支结构 `(seq, image_id, event)` 仍可能存在（`event TEXT NOT NULL`），
新事件写入使用 `event_type` 会失败；0023 必须识别并重建兼容表。

---

## 3. Migration 现状

`migration` 表 23 行，其中 22 个正式迁移 ID + 1 个历史分支同名记录：

| migration_id | version | status | 说明 |
|---|---|---|---|
| `0001_initial_schema` … `0020_review_session_end_reason` | 0.1.0–0.37.0 | applied | 历史迁移 |
| `0021_mobile_event_log_mutations` | 1.3.0 | applied | 主干 0021（W3.0 事件表 + 回执） |
| `0021_mobile_v2_events` | 0.38.0 | applied | 参考分支旧 0021（仅迁移记录，表结构已由 0022/手工修复归一） |
| `0022_mobile_v2_compat` | 1.3.1 | applied | 两套 0021 结构归一 |
| **0023** | 1.4.0 | **已实现，待正式库启动应用** | W4.1 新增：`mobile_image_events` 兼容重建（旧库/当前库/W4.0 快照副本均已演练） |

**约束：** 不得修改 0021/0022 文件或历史记录；0023 必须幂等，且在已修复库上安全跳过。

---

## 4. 关系与完整性检查

| 检查 | 结果 |
|---|---|
| `images` → `jobs` 外键 | 4,524 条生成图有 job；3,209 条导入图为 NULL，符合设计 |
| `images` → `job_items` 外键 | 4,524 条生成图有 job_item；0 条生成图缺 JobItem |
| `images.parent_image_id` 指向有效图片 | 32/32 有效，无悬空 |
| `image_variants.image_id` 指向有效图片 | 10,613/10,613 有效，0 悬空 |
| `image_variants` 文件存在 | 10,613/10,613 存在 |
| `images` 文件存在 | 7,733/7,733 存在 |
| `images.sha256` 与磁盘 | 3,209 条有值，0 不一致 |
| `prompt_versions.prompt_id` | 294/294 有效 |
| `prompts.current_version_id` | 294/294 有效，无悬空 |
| prompt ↔ image 关联 | 2,736 条，0 指向不存在的 Prompt |
| `mobile_review_session_items.image_id` | 全部指向有效图片（会话 5 个，项 5,389） |
| `mobile_image_seen` | 24 条，均指向有效图片 |
| 重复资源 ID | 无（各表主键/唯一索引均通过） |

---

## 5. 历史遗留与 W4.1 处理

| 遗留 | 影响 | 处理 |
|---|---|---|
| `mobile_write_receipts` 旧表仍在 | 旧客户端回执可能仍被 0022 合并逻辑读取 | 保留，不删除；0023 不触碰 |
| `migration` 同时存在两个 `0021` 记录 | 结构判断不能只看 migration_id | 0023 以 `PRAGMA table_info` 实际结构为准 |
| `images.review_status` 旧列与 `status` 新列并存 | 双写历史，语义已对齐 | 保留；写入继续双写 |
| 4,524 张引擎图无 `sha256` | 资产完整性统计缺 Hash | 迁移时计算并回填 |
| `jobs` 缺模型/工作流 manifest 快照 | 溯源依赖 Binding 文件与 Job hash | 新 Job 增加 `model_snapshot`；历史 Job 以 Job 身份 + Manifest 历史解释 |
| `prompts` 无 tags 表、无多版本 | 不满足 W4.1 字段标准 | 只读映射 + Manifest 标准；不新建重复表 |
| 13 个 INTERRUPTED Job | 依赖归档模型，不可续跑 | 保留记录，不删除、不改写 |

---

## 6. 容量与性能基线

| 项 | 值 |
|---|---|
| 数据库文件 | 123.3 MB |
| 最大表 | `job_events` 328,958 行 |
| 图片索引 | `images` 7,733；`image_variants` 10,613 |
| 图库分页现状 | 已存在 `limit/offset`；缩略图按需生成 |
| Prompt 图片查询 | 已使用 UNION + 批量窗口分页（v0.37），无 N+1 |

W4.1 只增量补统一统计与缓存路径，不重写现有分页核心。

---

## 7. 备份与回滚

- 数据库快照：`D:\NSFW-Studio-Data\backups\studio-20261104-103427.db`（SQLite backup API，WAL 安全）。
- DataRoot 副本：`D:\NSFW-Studio-Data-Backup-20261104`（排除 logs/cache/tmp）。
- 回滚方案：停止服务 → 用快照覆盖 `database/studio.db`（同时清理 `-wal/-shm`）→ 恢复 `images` 目录旧结构（迁移不删除旧文件）。
- 0023 回滚：保留迁移前数据库副本；0023 不删除 `mobile_image_events` 历史行，仅重建结构。
