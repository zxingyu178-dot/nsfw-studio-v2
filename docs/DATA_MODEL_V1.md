# DATA_MODEL_V1 — 数据模型设计（Phase 1，v0.2.0）

> 更新：2026-10-07。本文档是 Prompt / Asset / Recipe 数据模型的权威说明。

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
| （预留）Job/JobItem/Image | job_ / item_ / img_ | |

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

## 8. 未来 Job / Image 接入点（本阶段不实现）

| 接入点 | 说明 |
| --- | --- |
| `job_<uuid>` / `item_<uuid>` | Job 引用 `recipe_version_id`（完整快照即生成参数），执行结果产出 Image |
| `img_<uuid>` | Image 表挂 `job_item_id`，文件入 `images/originals/<img_id>/` |
| `assets.source_image_id` | 已预留列：图库上线后"从图库创建素材"回填 |
| `recipes.cover_image_id` | 已预留列：Recipe 封面图 |
| `asset_versions.reference_images_json` | 已预留：多参考图 |
| EngineAdapter / WorkflowModule | Job 执行链路走已收口的异步契约 |
