# W4.1 — 统一资源与资产架构

> 状态：W4.1 正式架构 · 基线 `9904e12` · 2026-11-04
> 本文件说明四个资源中心的职责、唯一真源、存储结构、数据库关系与 API 边界。
> 任何 AI Agent / 开发者新增资源前必须先读本文件与 `AGENT_SUBMISSION_STANDARD.md`。

---

## 1. 四个中心

| 中心 | 职责 | 定义真源 | 运行真源 |
|---|---|---|---|
| Model Center | 模型身份、版本、文件、Hash、依赖、安装/归档状态 | `registry/models/**/model.yaml`（Git；支持 `<id>/model.yaml` 与 `<id>/<version>/model.yaml`） | 本地扫描（大小 + SHA256）+ ComfyUI `/models`（DB 不复制定义） |
| Workflow Center | 工作流/绑定身份、输入输出、默认参数、依赖、Hash、放行状态 | `registry/workflows/**/manifest.yaml` + `workflows/providers/**`（Git） | `configs/workflow.yaml` 选择默认 binding；`workflows/release_manifest.yaml` 记录 Gate 证据 |
| Prompt Center | Prompt 标题、版本、结构化字段、标签、收藏、评分、图片关联 | `registry/schemas/prompt.schema.json` + 既有 ORM | `prompts` / `prompt_versions` / `prompt_evaluations` |
| Image Asset Center | 图片资产身份、存储、Hash、派生关系、审核/收藏、生成溯源 | `registry/schemas/asset.schema.json` + 既有 `images` ORM | `images` / `image_variants` + DataRoot 文件 |

四个中心共享同一套：ID 标准、版本标准、Manifest 标准、存储标准、DB 关联、API、Agent 提交、迁移标准。

---

## 2. 唯一真源划分

```text
Git
├── registry/schemas/            # Schema 定义（版本化）
├── registry/models/             # 模型身份/版本/文件/Hash（不含物理模型）
├── registry/workflows/          # 工作流/绑定定义（活动 + 历史）
├── workflows/providers/         # workflow.json + binding.yaml（执行文件）
└── workflows/release_manifest.yaml  # 仅放行/Gate 证据，不重复定义

数据库（DataRoot/database/studio.db）
├── 运行状态：jobs / job_stages / job_items / job_stage_items / job_events
├── 业务记录：prompts / prompt_versions / images / image_variants
└── 审核与移动端：mobile_review_* / mobile_image_events / mobile_mutation_receipts

文件系统（DataRoot）
├── assets/images/YYYY/MM/<asset_id>/<kind>.<ext>   # 正式图片
├── cache/thumbnails/<asset_id>/thumbnail.webp      # 派生缓存
├── cache/previews/<asset_id>/preview.webp
├── database/、backups/、logs/、imports/、exports/
└── archive/（旧结构只读保留）
```

**禁止**：在数据库里再复制一份与 Manifest 永久冲突的模型/工作流定义；
**禁止**：前端维护第二份工作流/模型配置；
**禁止**：把机器绝对路径写入 Git 或数据库。

---

## 3. 数据流

### 3.1 生成链

```text
Workbench（前端）
  → POST /api/v1/jobs（JobService：冻结快照 + PipelineValidator）
  → 单队列 Worker（唯一队列 / 唯一 Worker）
  → WorkflowModule → EngineAdapter(ComfyUI)
  → Image Asset Ingest（AssetIngestService）
  → images / image_variants + mobile_image_events（同事务）
  → Gallery / Prompt Library / MediaReview（同一份资产）
```

### 3.2 资源读取链

```text
前端
  → GET /api/v1/modules            # 工作台唯一入口（Workflow Center 投影）
  → GET /api/v1/registry/workflows # 资源管理/诊断（只读）
  → GET /api/v1/registry/models    # 模型登记与安装状态
  → GET /api/v1/images             # Image Asset Center
  → GET /api/v1/images/{id}/provenance # Prompt / 工作流 / 模型 / 引擎版本追溯
  → GET /api/v1/prompts            # Prompt Center
  → GET /api/v1/prompts/{id}/center# 统一投影（版本/结构化字段/tags/rating）
  → GET /api/v1/prompts/{id}/images# 全量关联图片分页
```

---

## 4. 数据库关系

```text
prompts 1 ─ n prompt_versions
   │                 │
   └─ Job.workbench_snapshot_json.source_prompt_id / source_prompt_version_id

jobs 1 ─ n job_items（seed）
     1 ─ n job_stages（module/provider/binding/workflow_hash/binding_hash）
     1 ─ n images
images
  ├─ job_item_id → job_items.id
  ├─ parent_image_id → images.id（派生关系）
  └─ n image_variants（thumbnail / preview）
images.sha256 / metadata_json(mime_type, file_size, module_id, v1_output)
```

- `images.file_path` 即 `storage_key`，永远是 DataRoot 相对路径；
- 不新增重复业务表；`asset_type` 由 `source` + `kind` 投影：
  `import` → `imported`；`original/processed/upscaled` → 同名；其余 → `other_variant`；
  `parent_asset_id` = `parent_image_id`；
- Prompt 与图片的双通道关联（Job 快照 + 导入元数据）保留，不做第二套关系表；
- 历史 `kind=upscaled` 与 `image_variants` 历史类型继续可读；
- `workflow_snapshot_json` 额外记录 `engine_version`（Job 创建时 preflight 实测值；历史 Job 缺失为 null）。

---

## 5. API 与服务边界

| 服务 | 职责 | 不允许 |
|---|---|---|
| `ModelRegistryService` | 加载/校验模型 Manifest；解析文件、Hash、安装状态 | 下载/移动模型；写 DB 定义副本 |
| `WorkflowRegistryService` | 加载/校验工作流 Manifest；解析依赖与放行状态 | 绕过 `release_manifest.yaml` 私自放行 |
| `RegistryValidator` | Schema、唯一性、版本、Hash、依赖、路径穿越、未知字段 | 静默接受未知字段或未知依赖 |
| `PromptService` / `PromptCenterService` | 版本不可变、结构化字段映射、统计、批量关联 | 覆盖历史版本；N+1 查询 |
| `AssetIngestService` | 所有新图片的唯一写入入口：校验、Hash、存储、DB、事件 | 模块自行写 `images` 表 |
| `AssetStorageService` | `storage_key` ↔ 绝对路径、原子写、缓存路径 | 业务代码直接拼路径 |
| `AssetQueryService` | 资产统计、缺失/孤立识别、分页查询 | 删除孤立文件 |
| `GenerationProvenanceService` | Job/模型/工作流/Prompt/Seed/输出资产追溯 | 改写历史 Job 身份 |

错误码统一：`REGISTRY_*`、`ASSET_*`、`PROMPT_*`、`WORKFLOW_*`；所有响应遵循现有 `{code, message, details}`。

---

## 6. 统一 ID 与版本

| 资源 | ID 形式 | 版本形式 | 不可变规则 |
|---|---|---|---|
| 模型 | `model_id`：`^[a-z0-9][a-z0-9_]*$` | 语义版本 `1.0.0`；同 ID 可并存多版本目录 | 已发布版本不可原地覆盖 |
| 工作流 | `workflow_id`：现有模块名 | `vN`（binding） | 已发布 binding 不可覆盖 |
| Prompt | `prm_<uuid>` | 整数 `version_no`，从 1 递增 | 版本只 INSERT |
| 图片资产 | `img_<uuid>` | 无版本；派生图为新 asset | 不覆盖原图 |
| Job | `job_<uuid>` | 执行身份 = workflow_hash + binding_hash | 历史 Job 不改写 |

模型多版本解析规则：`get_model(model_id)` 默认返回最高语义版本；`version` 显式指定时精确匹配；
同一 `(model_id, version)` 在活动/归档目录重复 → `DUPLICATE_MODEL_VERSION`，禁止覆盖历史版本。

---

## 7. 统一 Hash 标准

| 算法 | 标识 | 用途 |
|---|---|---|
| 原始字节 | `raw-bytes-v1` | 历史 Binding / 历史 Job 身份验证 |
| LF 规范化 | `lf-normalized-v1` | W4.1 起新 Job / Manifest / 跨平台校验 |

规则：
1. 新 Manifest 记录 `lf-normalized-v1` 值；
2. `legacy_raw_workflow_hash` / `legacy_raw_binding_hash` 保留历史树观测到的原始值；
3. `ComfyUIAdapter.load_binding` 同时接受 raw 与 LF；不匹配才拒绝；
4. 历史 Job 的 `workflow_hash` / `binding_hash` 原样保留，不批量改写；
5. `.gitattributes` 固定 JSON/YAML 为 LF，但不 renormalize 已发布 Binding。

### 7.1 运行依赖校验（§4.5）

`RuntimePreflightService` 在每次 Job 创建前执行：

1. 解析 workflow.json 中的模型 Loader（`UnetLoaderGGUF` / `UNETLoader` / `CheckpointLoaderSimple` /
   `CLIPLoader` / `VAELoader` / `LoraLoader*` / `UpscaleModelLoader`）；
2. 未知 Loader → `UNKNOWN`，不得 READY；
3. Binding `requirements.models` 必须已在 Model Center 登记且 `released`；
4. 配置 `model_registry.search_roots` 时，对本机文件校验 **存在性 + 大小 + SHA256**
   （`verify_hash: true`，Hash 按 path+size+mtime 缓存在 `DataRoot/cache/registry_model_hashes.json`）；
5. 任一缺失/大小或 Hash 不一致 → `BLOCKED`；无法验证 → `UNKNOWN`；两者都不得放行 Job。

---

## 8. 存储标准

```text
DataRoot/
├── assets/
│   └── images/
│       └── YYYY/MM/<asset_id>/
│           ├── original.png|jpg|webp
│           ├── processed.png|jpg|webp
│           └── upscaled.png|jpg|webp      # 仅历史
├── cache/
│   ├── thumbnails/<asset_id>/thumbnail.webp
│   ├── previews/<asset_id>/preview.webp
│   └── temp/
├── imports/ exports/ backups/ database/ logs/
└── archive/images-legacy-YYYYMM/          # 旧结构只读保留
```

- 数据库只存 `storage_key`（相对路径），不存盘符；
- 缓存不是唯一存储：原图缺失时缓存不能替代；
- 缓存键 = `asset_id` + variant_type + 尺寸参数；缺失可重建；
- 旧 `images/originals|upscaled|processed|thumbnails|previews` 在迁移验收后整体归档，不直接删除。

---

## 9. 历史兼容红线

1. 不删除历史图片 / Prompt / Job / JobStage / JobItem；
2. 不覆盖冻结 Binding；
3. 历史 `upscaled` 图片与父子关系继续可读；
4. 不重写 0021 / 0022；0023 只做结构兼容重建；
5. 不批量移动文件；复制 + SHA256 校验后才更新数据库；
6. 手机 MediaReview V2 合同、设备权限、增量事件、幂等回执不变。
