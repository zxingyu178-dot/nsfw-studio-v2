# W4.1 — Unified Resource & Asset Architecture 阶段报告

> 项目：`nsfw-studio-v2` · 日期：2026-11-06 · 基线：`9904e126a1fa182a8506285e0bf990308a575495`
> 状态：**W4.1 全部 Gate 完成并通过验收**；最终提交与 CI 见第 7 节。

---

## 1. 交付摘要

| 项 | 状态 |
|---|---|
| 四大资源中心 | 已建立（Model / Workflow / Prompt / Image Asset） |
| 统一 ID / 版本 / Manifest / 存储 / DB 关联 / API / Agent 提交标准 | 已完成 |
| 30 个模型 Manifest | 6 活动 + 24 归档 |
| 10 个工作流 Manifest | 4 活动 + 5 冻结 + 1 归档 |
| Registry Validator | `checked=40 errors=0 warnings=7` |
| 历史图片迁移 | 7,733 图 + 10,613 变体；0 缺失 / 0 Hash 不一致 / 0 孤立 |
| 0023 Migration | 旧库/当前库/W4.0 快照副本演练通过 |
| 后端定向测试 | 通过 |
| 前端 build / vitest | 通过 / 488 通过 |
| 后端全量 pytest | 718 collected；退出码 0；1 skipped（既有环境跳过项） |
| G3 / G4 | 完成（8 个冷/热 Job + 4 个峰值采样 Job，全部 COMPLETED） |
| 实时生产验证 | 四模块 Preflight READY + 1 个真实 Job COMPLETED，快照含 engine_version |
| GitHub CI / Commit SHA | 见第 7 节 |

---

## 2. 四大中心

### 2.1 Model Center
- `registry/models/**/model.yaml`：模型 ID、版本、文件、大小、SHA256、依赖、状态；
- 支持 `models/<id>/model.yaml` 与 `models/<id>/<version>/model.yaml` 两种布局；
  同一 `model_id` 可并存多个版本，默认取最高版本，重复 `(model_id, version)` 报错；
- 6 个活动模型全部 `released` 且 SHA256 非 `unverified`；
- 24 个归档模型状态 `archived`，登记保留、文件不进入 Git；
- 本机安装状态通过 `GET /api/v1/registry/models?workflow_id=` 查询（兼容工作流过滤）；
- Preflight 对正式 Binding 声明模型校验存在性 + 文件大小 + SHA256；
  未登记 → UNKNOWN，缺失/大小或 Hash 不一致 → BLOCKED，不静默 READY。

### 2.2 Workflow Center
- `registry/workflows/**/manifest.yaml`：输入/输出、默认参数、模型依赖、双 Hash、放行状态；
- 活动：`basic_generate/v2`、`anime_generate/v2`、`img2img/v3`、`reference_generate/v2`；
- 历史：`basic v1`、`anime v1`、`img2img v1/v2`、`reference v1`、`upscale/v1`；
- `/api/v1/modules` 增加 Registry 投影；前端不维护第二份工作流配置。

### 2.3 Prompt Center
- 294 Prompt / 294 版本；0 无版本、0 多版本、0 悬挂；
- 254 个 Prompt 有图片关联，共 2,736 条链接；
- 字段映射 `face→character / pose→action / composition→camera`，原字段保留；
- 标准字段 `tags`（存 `structured_json`，不新建表）与 `rating`（最新评分）已纳入
  `PromptResponse` 与 `GET /api/v1/prompts/{id}/center`；
- `GET /api/v1/prompts/stats` 提供统计；图片分页与预览分离。

### 2.4 Image Asset Center
- 新图片统一 `AssetIngestService` → `assets/images/YYYY/MM/<asset_id>/<kind>.<ext>`；
- 缩略图/预览统一 `cache/thumbnails` / `cache/previews`；
- 全部 7,733 张图片已有 SHA256、mime_type、file_size、asset_type；
- `asset_type` 投影：`imported` / `original` / `processed` / `upscaled` / `other_variant`；
- 派生图父子关系 32 条保留；
- `GET /api/v1/images/{id}/provenance` 返回 Prompt / 工作流 / 模型快照 / 引擎版本；
- `GET /api/v1/registry/assets` 提供完整性统计（含缺失、孤立、缩略图缺失、Prompt 关联/未关联）。

---

## 3. 历史迁移

| 项 | 迁移前 | 迁移后 |
|---|---:|---:|
| images | 7,733 | 7,733 |
| image_variants | 10,613 | 10,613 |
| prompts / versions | 294 / 294 | 294 / 294 |
| jobs | 946 | 946 |
| job_items / job_stages | 6,720 / 954 | 6,720 / 954 |
| 父子关系 | 32 | 32 |
| mobile_image_events | 8,006 | 8,006 |
| 图片缺失 | 0 | 0 |
| SHA256 不一致 | — | 0 |
| 孤立文件 | 0 | 0 |

完整报告：`W4_1_IMAGE_MIGRATION.md`、`W4_1_RELATIONSHIP_REPORT.md`、`W4_1_MIGRATION_RISK.md`。

---

## 4. 技术修复

### 4.1 Migration 0023
- 识别 `mobile_image_events` 旧结构（`event TEXT NOT NULL` / 缺 `event_id` / 缺 `event_type`）；
- 重建主干结构，保留全部事件行与 `seq`，重建索引与唯一约束；
- 已修复库安全跳过；0021/0022 未修改；
- 演练：旧结构 3 行、当前库 8,006 行、W4.0 快照 8,002 行，均保持行数并成功写入新事件。

### 4.2 LF/CRLF Hash
- 新增 `lf-normalized-v1` 与 `raw-bytes-v1` 双算法；
- `load_binding` 同时接受 raw/LF，历史 Job 不受影响；
- `.gitattributes` 固定 JSON/YAML 为 LF，不 renormalize 已发布 Binding；
- Job 快照新增 `hash_algorithm` 与 `model_snapshot`。

### 4.3 运行依赖与模型多版本
- Model Center 支持同一 `model_id` 多版本目录，重复版本拒绝；
- Model Manifest 支持 `dependencies`（依赖未登记 → `MODEL_DEPENDENCY_UNKNOWN`）；
- Preflight 对 Binding 声明模型执行本机文件大小 + SHA256 校验（Hash 缓存），
  依赖缺失不得 READY；未知 Loader 继续返回 UNKNOWN；
- 工作流依赖模型必须已登记，活动工作流要求 `released`。

### 4.4 统一生成快照与资产溯源
- `workflow_snapshot_json` 新增 `engine_version`（Job 创建时 preflight 实测版本）；
- Job 快照继续包含 `model_snapshot`、`hash_algorithm`、Prompt 快照、Seed；
- `GET /api/v1/images/{id}/provenance` 增加
  `prompt_id / prompt_version_id / workflow_id / workflow_version / model_snapshot / engine_version`；
- 最终拼接文本 = `jobs.positive_prompt_snapshot`；素材关键词 = `workbench_snapshot_json.selected_assets`，
  两者均随 Job 冻结，不依赖当前工作台状态。

---

## 5. 测试与验收

| 项目 | 结果 |
|---|---|
| 后端全量 pytest | 718 collected；退出码 0；1 skipped |
| 前端 build | 通过（13.22s） |
| 前端 vitest | 488 passed / 97 files |
| G0 静态校验 | `checked=9 errors=0 warnings=12`（历史冻结 Binding 既有 warning） |
| Registry Validator | `checked=40 errors=0 warnings=7` |
| 四模块 Preflight | `status=READY`；每个声明模型 `installed` + `sha256_verified=true` |
| 模型 SHA256 | 6/6 installed，大小与 Hash 全部一致（首次 130.73s，之后缓存命中） |
| 0023 正式库 | `latest_migration=0023_mobile_event_legacy_repair` |
| 图库读取 | `GET /images` total=7,746；缩略图 200；原图 200 |
| Prompt Center | `GET /prompts` total=292（默认排除归档）；关联图片分页可用 |
| Image Asset 统计 | `total=7,746`；`missing_files=0`；`thumbnails_missing=0` |
| 手机端 | 66 项 mobile 合同测试通过（独立临时 DataRoot） |
| 实时生成 | Job `job_f6de2b35-...` COMPLETED；输出 `img_905e9fb5-...` |
| GitHub CI | 见第 7 节 |

### 5.1 G3 四条工作流真实出图（冷启动）

| 模块 | Job | workflow_hash (LF) | binding_hash (LF) | 输出 | 尺寸 | 耗时 |
|---|---|---|---|---|---|---|
| basic_generate/v2 | `job_bf7490c6-55b5-4e33-8b69-99ebf3a8d876` | `af870a6442432dfd` | `d9ca1eba6c482f57` | `img_02917c97-...` | 832×1216 | 670.7s（冷） |
| anime_generate/v2 | `job_2b2a8e90-9047-4759-8b5c-0adadb976a9f` | `db2bd841c260a434` | `7832e2b669aa1c44` | `img_8ba43ec8-...` | 832×1216 | 130.5s（冷） |
| img2img/v3 | `job_5500fbc7-b5f5-47d3-9f26-a607cae02564` | `c94f28966da4db41` | `21d056e2f9e7db77` | `img_5fdf7923-...` | 832×1216 | 423.0s（冷） |
| reference_generate/v2 | `job_3c77f1ff-f1e0-4b97-bc98-74dd95a9a2c5` | `88007850182aff4d` | `cfc68ee2f803c9ed` | `img_edc3a55a-...` | 640×928 | 685.0s（冷） |

### 5.2 G4 冷/热与资源峰值

| 模块 | 冷启动 | 热启动 | GPU 峰值 | RAM 峰值 | OOM |
|---|---:|---:|---:|---:|---|
| basic_generate/v2 | 670.7 s | 82.7 s | 5,903 MB | 16,268 MB | 否 |
| anime_generate/v2 | 130.5 s | 36.4 s | 5,428 MB | 15,808 MB | 否 |
| img2img/v3 | 423.0 s | 101.1 s | 5,488 MB | 16,156 MB | 否 |
| reference_generate/v2 | 685.0 s | 119.2 s | 5,486 MB | 16,265 MB | 否 |

- 引擎从完全停止状态启动：329.6 s 上线（ComfyUI 0.37.0）；
- 共 12 个验收 Job（8 个冷/热 + 4 个峰值采样），全部 `COMPLETED`，失败率 0；
- 峰值采样在模块切换后的运行中采集，包含模型加载阶段；耗时列中的“热”为同模块连续第二跑；
- 已据此把四个活动 binding 的 `default_profile_verified` 置为 `true`。

---

## 6. 已知限制

1. 冷启动耗时受机械盘模型加载影响很大（basic 670s / reference 685s），不代表稳态吞吐。
2. 旧 `images/*` 目录未归档/未删除，目前与新资产并存（约 14 GB）；资产统计以
   `legacy_retained_files/bytes` 单独标记，不混入孤立清单。
3. 历史 Job 缺 `model_snapshot` / `engine_version`，Provenance 明确标记，不伪造。
4. 峰值采样为 1 秒粒度，可能低估瞬时峰值；未记录 nvidia-smi 功耗/温度。
5. 首次实时验收生成出现一次 `ENGINE_NETWORK`（ComfyUI `/history` 请求失败），同条件重试成功；
   判定为模型加载期间瞬态网络失败，已如实保留。
6. 手机端 Bridge 在最终态未自动启动（配置关闭），实时健康标记为“未执行”；
   手机端验证依据为 66 项隔离 DataRoot 合同测试。
7. 未新增 4x / SeedVR2 / 新工作流 / 新模型。

---

## 7. 交付状态

| 项 | 结果 |
|---|---|
| 功能提交 | `645649d` |
| 证据/放行提交 | `cb946eb` |
| 完成度补齐提交 | `288bd7d`（多版本/Hash 校验/tags/provenance/engine_version/统计） |
| CI 修复提交 | `e6069c1`（历史快照形状 + 外部 registry 根） |
| 验收报告提交 | `99251d2` |
| GitHub CI（`99251d2`） | main `42261666849` success；develop `42261689819` success |
| 放行状态（现场 API） | 四模块 `ready_to_run=true`、`default_profile_verified=true` |
| 实时生成（现场） | `job_f6de2b35-...` COMPLETED；`engine_version=0.37.0` |
| 验收包 | `D:\AIHome_2.0_L1_L2\archive\NSFW_Studio_W4.1_Review_Package.zip` |

已完成：Gate 0、Gate 1、四个中心代码、0023、Hash 兼容、历史迁移、G3/G4、前端与 CI、
实时部署验收、验收报告与 ZIP。
**本阶段到此停止，不进入 W4.2。**
