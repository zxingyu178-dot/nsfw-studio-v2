# DATA_MODEL_V1 — 数据模型设计（Phase 1 + 2 + 3 + 4 + 5 + 5.1 + 6，v0.8.0）

> 更新：2026-10-08。本文档是 Prompt / Asset / Recipe / Job / Image 数据模型的权威说明；
> Job 状态机见 docs/JOB_STATE_MACHINE.md，Image 细节见 docs/IMAGE_MODEL.md，
> 多阶段管线见 docs/PIPELINE_V2.md，迁移见 docs/DATABASE_PLAN.md 与 docs/MIGRATION_0008_BACKFILL.md。

## 1. ER 图

```text
prompts 1 ──── * prompt_versions
   │                  ▲
   │ current_version_id（指针，指向最新版）
   │
   │ (来源 FK，可选)
   │
recipes 1 ──── * recipe_versions * ──── 2..4 recipe_asset_snapshots * ──── 1 asset_versions
   │                │                                            │
   │                └── source_prompt_version_id ───────────────┼── assets
   │ cover_image_id (nullable, 图库阶段)                         │
   ▼                                                            ▼
 (未来 Image)                                          assets 1 ──── * asset_versions
```

- `prompts.current_version_id` / `assets.current_version_id` / `recipes.current_version_id`
  是**指针**（无数据库 FK，应用层维护），指向当前版本；
- Version 表之间互相独立，均 immutable；
- `recipe_asset_snapshots` 同时持有 `asset_id` + `asset_version_id` FK 与内容快照。

## 2. 统一 ID（规范 §四）

| 对象 | 前缀 | 示例 |
| --- | --- | --- |
| Prompt / PromptVersion | prm_ / prmv_ | `prm_1f0e...` |
| Asset / AssetVersion | ast_ / astv_ | `ast_9c2a...` |
| Recipe / RecipeVersion | rcp_ / rcpv_ | `rcp_55d1...` |
| RecipeAssetSnapshot | rcpas_ | |
| Job / JobItem | job_ / item_ | `job_7a31...`（Phase 2） |
| JobEvent | 自增 INTEGER PK（仅审计，不作外部 ID） | |
| Image | img_ | `img_b204...`（Phase 2C） |

数据库一律 `TEXT PRIMARY KEY`，不使用自增整数作为外部业务 ID。

## 3. Version 机制

- 内容变化（正向 / 负向 / 结构化字段 / 模式 / 素材内容）→ **INSERT 新版本**，version_no = max+1；
- 元数据变化（名称 / 收藏 / 归档）→ 只改父表，**不建版本**；
- 内容完全不变 → 不建冗余版本；
- **版本 immutable**：Service 层禁止 UPDATE 任何 Version 表内容；
- 恢复旧版本 = 复制其内容创建新的最新版（历史永远线性：v1 v2 v3 → 恢复 v1 → v4）；
- 并发保护：`UNIQUE(parent_id, version_no)` + 单事务，冲突 → `VERSION_CONFLICT`（409）。

## 4. Snapshot 机制

- **Prompt 快照**（RecipeVersion）：`source_prompt_id` / `source_prompt_version_id` FK 知来源，
  `positive/negative/structured` 快照列保证历史不变——Prompt 升级不影响老 Recipe；
- **素材快照**（RecipeAssetSnapshot）：每个 slot 最多一条（`UNIQUE(recipe_version_id, slot)`），
  锁定具体 `asset_version_id`，并复制当时的 `asset_name / prompt / preview_path`；
- 老素材升级到新版本，老 RecipeVersion 仍打开当时的版本，不偷偷升级。

## 5. 软删除规则

- `archived = 1` 为软删除；普通 UI 不提供物理删除；
- 列表默认过滤 archived，可显式查询；
- 归档/恢复只改父表，不触碰版本。

## 6. 结构化 Prompt（八部分，顺序永久固定）

```text
style(风格) → face(人脸) → clothing(服饰) → pose(动作) → scene(场景)
→ composition(镜头/构图) → lighting(光线) → extra(额外描述)
```

- 存储为 canonical JSON（八字段齐全、去除首尾空白、未知字段丢弃）；
- 最终正向 Prompt 由**后端 PromptComposer 统一合成**（`", "` 连接，跳过空字段）；
- 前端预览调用 `POST /api/v1/prompts/compose`，与保存同源。

## 7. 文件引用规则（Asset）

```text
DataRoot/assets/<type>/<asset_id>/v<0001>/preview.<ext>
```

- 数据库只存 **DataRoot 相对路径**（POSIX 分隔符），禁止绝对路径；
- 解析一律经 `StorageManager.resolve_under()` / `absolutize()`（防穿越、防绝对路径、防 `..`）；
- 写入流程：上传 → `images/temp`（校验扩展名+MIME+magic bytes+大小≤10MB）→ 原子移动 → 数据库提交；
  提交失败删除正式文件，文件失败绝不先提交数据库；
- 旧版本文件永不覆盖、永不删除。

## 8. Job / Image（Phase 2 已实现）

### 8.1 Job / JobItem / JobEvent（0005_job）

```text
jobs 1 ──── * job_items
  │               │ image_id ──→ images.id（导入完成回填）
  │               └ engine_job_id（引擎任务 id，崩溃恢复核对用）
  ├── workbench_snapshot_json     提交时固化的 WorkbenchSnapshot
  ├── positive/negative_prompt_snapshot + structured_prompt_snapshot
  ├── generation_settings_json    尺寸 / 数量 / seed_mode / seed
  ├── module_id / module_version / provider / binding_version / workflow_hash / binding_hash（§五十五；Task1）
  ├── requested_count / completed_count / queue_position / priority
  ├── resume_of_job_id   → 续跑父子关系（§二十）
  ├── pause_requested / cancel_requested / error_type / error_message
  └── UNIQUE(source, client_request_id)  外部幂等（§十二）

job_events 1 ──── * 追加型审计（event_type / payload_json / created_at）
images 1 ──── * parent_image_id 自引用（派生图溯源）
```

- **快照纪律（§十）**：Job 提交后，Prompt / Recipe / Asset 的后续修改都不影响该 Job；
- **Seed（§九）**：Item 执行时分配；成功 Item 的 Seed 永远保留；
  **续跑子 Job 一律新随机 Seed**（`count=remaining, seed_mode=random, seed=null`，Phase 2.1 §五）；
- **Workflow 快照（Phase 2.1 §四；Phase 4 Task1/9）**：`workflow_snapshot_json.modules` 由后端按实际执行的
  模块身份写入（module_id / module_version / provider / binding_version / workflow_hash / binding_hash），
  不允许"执行了模块但 modules=[]"；从历史恢复时该快照整体作为固定身份回传，提交时按原版本执行；
- 状态机与事件清单见 docs/JOB_STATE_MACHINE.md / docs/QUEUE_SPEC.md。

### 8.2 Image（0006_image；0010_image_inputs，Phase 5）

`img_<uuid>`，挂 `job_id / job_item_id`（外部导入时为 NULL），文件入
`images/originals/<img_id>/original.<ext>`（DataRoot 相对路径入库）；
审核 `UNREVIEWED / KEPT / REJECTED` + 独立 `favorite`；详见 docs/IMAGE_MODEL.md。

Phase 5 新增列（0010_image_inputs）：

| 列 | 说明 |
| --- | --- |
| `images.sha256` | 外部导入文件内容哈希（去重依据；+`idx_images_sha256`；**Phase 5.1 起 `uq_images_import_sha256` 部分唯一索引兜底并发**——`source='import' AND sha256 IS NOT NULL`）；引擎输出为 NULL |
| `images.imported_filename` | 外部导入原始文件名（仅用于展示 / 搜索；**绝不作为文件引用**） |

### 8.3 预留列现状

| 接入点 | 状态 |
| --- | --- |
| `assets.source_image_id` | ✅ Phase 2C 启用：从图库创建素材时回填 |
| `images.parent_image_id` | ✅ Phase 3 启用：高清图（upscaled）指向来源原图 |
| `recipes.cover_image_id` | 预留：Recipe 封面图（未启用） |
| `asset_versions.reference_images_json` | 保持预留（历史兼容读回落）；**Phase 5 起参考图改用正式关系表** `asset_reference_images`（见 8.5） |
| `job_stage_items.seed` | ✅ Phase 4 启用：StageItem 真实 Seed（溯源以它为准） |
| `recipe_versions.input_images_json` | ✅ Phase 5 启用：输入图快照 `[{role, image_id, sha256}]`（max=1） |
| EngineAdapter / WorkflowModule | ✅ Phase 2 真实接入（ComfyUIAdapter + provider binding）；Phase 3 多模块动态绑定；Phase 4 能力驱动 I/O + 输入图片正式契约；Phase 5 能力声明补充 input_required/input_role |

### 8.4 JobStage / JobStageItem（0007_pipeline_stage，Phase 3；0008/0009，Phase 4）

```text
JobStage（job_stages）           一个阶段（固化 module/binding/双指纹）
  ├─ stage_index / module_id / module_version / provider / binding_version /
  │  workflow_hash / binding_hash（Phase 4 Task1）
  ├─ status（QUEUED/RUNNING/COMPLETED/FAILED/CANCELLED/INTERRUPTED）
  ├─ total_count / completed_count / config_json（如 execution_timeout）
  └─ JobStageItem（job_stage_items）
       ├─ job_item_id / item_index（一个逻辑槽位）
       ├─ input_image_id / output_image_id（图片流转）
       ├─ seed（Phase 4 Task3：uses_seed=false 的 Stage 为 NULL）
       ├─ status / engine_job_id / progress / error_* / retry_count
       └─ 崩溃恢复粒度（§八）
```

- 执行真源 = JobStage + workflow_snapshot（Job 创建后当前配置不再影响该 Job）；
- `UNIQUE(job_id, stage_index)`；`jobs.job_kind`：generate / process；
- 历史 Job（v0.3.x）由 `0008_pipeline_backfill` 回填 Stage0（身份继承 Job 列），
  `0009_execution_fingerprint` 增加 binding_hash / StageItem.seed 并修正历史假 Seed；
- 详见 `PIPELINE_V2.md`、`PIPELINE_STATE_MACHINE.md`、`MIGRATION_0008_BACKFILL.md`。

### 8.5 AssetReferenceImage（0010_image_inputs，Phase 5 §十二/§十三）

```text
asset_reference_images
  ├─ id（arimg_<uuid>）
  ├─ asset_version_id → asset_versions.id（版本不可变：参考图变化 = 新版本）
  ├─ image_id         → images.id（统一 image_id，不复制外部文件）
  ├─ role             Phase 5 固定 face_reference（仅 Face Asset 可绑定）
  ├─ sort_order       Phase 5 固定 0（单张；未来多图按 sort_order 扩展）
  └─ UNIQUE(asset_version_id, role, sort_order) + 2 索引
```

- 绑定 / 更换参考图 = 创建新 AssetVersion（旧版本保留自己的参考图）；
  不传 `reference_image_id` 时沿用当前版本参考图（与 preview 沿用语义一致）；
- API 响应 `AssetVersionResponse.reference_images` 来自本关系表（图片 image_id 列表）；
  非 face 类型绑定 → 400 `ASSET_REFERENCE_TYPE_INVALID`；图片不存在 → 404 `IMAGE_NOT_FOUND`。
