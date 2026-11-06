# W4.1 — Unified Resource & Asset Architecture 阶段报告

> 项目：`nsfw-studio-v2` · 日期：2026-11-04 · 基线：`9904e126a1fa182a8506285e0bf990308a575495`
> 状态：**核心实现与历史资产迁移完成；全量测试/G3/G4/CI 进行中**，未虚标完成项。

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
| 后端全量 pytest | 697 collected；1 个 SSE 启动超时用例（单测复跑通过），1 skipped |
| G3 / G4 | 完成（8 个冷/热 Job + 4 个峰值采样 Job，全部 COMPLETED） |
| GitHub CI / Commit SHA | `645649d` / CI `41789128325` success |

---

## 2. 四大中心

### 2.1 Model Center
- `registry/models/**/model.yaml`：模型 ID、版本、文件、大小、SHA256、依赖、状态；
- 6 个活动模型全部 `released` 且 SHA256 非 `unverified`；
- 24 个归档模型状态 `archived`，登记保留、文件不进入 Git；
- 本机安装状态通过 `GET /api/v1/registry/models` 查询；
- Preflight 对正式 Binding 声明的未登记模型返回 UNKNOWN，不静默 READY。

### 2.2 Workflow Center
- `registry/workflows/**/manifest.yaml`：输入/输出、默认参数、模型依赖、双 Hash、放行状态；
- 活动：`basic_generate/v2`、`anime_generate/v2`、`img2img/v3`、`reference_generate/v2`；
- 历史：`basic v1`、`anime v1`、`img2img v1/v2`、`reference v1`、`upscale/v1`；
- `/api/v1/modules` 增加 Registry 投影；前端不维护第二份工作流配置。

### 2.3 Prompt Center
- 294 Prompt / 294 版本；0 无版本、0 多版本、0 悬挂；
- 254 个 Prompt 有图片关联，共 2,736 条链接；
- 字段映射 `face→character / pose→action / composition→camera`，原字段保留；
- `GET /api/v1/prompts/stats` 提供统计；图片分页与预览分离。

### 2.4 Image Asset Center
- 新图片统一 `AssetIngestService` → `assets/images/YYYY/MM/<asset_id>/<kind>.<ext>`；
- 缩略图/预览统一 `cache/thumbnails` / `cache/previews`；
- 全部 7,733 张图片已有 SHA256、mime_type、file_size、asset_type；
- 派生图父子关系 32 条保留；
- `GET /api/v1/registry/assets` 提供完整性统计。

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

---

## 5. 测试与验收

| 项目 | 结果 |
|---|---|
| 后端全量 pytest | 697 collected；仅 1 个 SSE 测试在磁盘高负载时启动超时（单测复跑通过）；1 skipped |
| 前端 build | 通过（15.35s） |
| 前端 vitest | 488 passed / 97 files |
| G0 静态校验 | `checked=9 errors=0 warnings=12`（历史冻结 Binding 既有 warning） |
| Registry Validator | `checked=40 errors=0 warnings=7` |
| 四模块 Preflight | `status=READY`（basic / anime / img2img / reference 全 READY） |
| 0023 正式库 | `latest_migration=0023_mobile_event_legacy_repair` |
| 图库读取 | `GET /images` total=7,733；缩略图 200；原图 200 |
| Prompt Center | `GET /prompts` total=292（默认排除归档）；关联图片分页可用 |
| Image Asset 统计 | `total=7,733`；模型登记 6 个活动模型 |
| 手机端 | 全量 pytest 中 mobile 合同测试通过；Bridge 启动运行态健康 `api_contract=2` |
| GitHub CI | `41789128325` @ `645649d` success |

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

1. 全量 pytest 存在 1 个磁盘高负载下的 SSE 启动超时 flake（单测复跑通过）；CI 独立环境已全绿。
2. 冷启动耗时受机械盘模型加载影响很大（basic 670s / reference 685s），不代表稳态吞吐。
3. 旧 `images/*` 目录未归档/未删除，目前与新资产并存（约占 14 GB）。
4. 历史 Job 缺 `model_snapshot`，Provenance 明确标记，不伪造。
5. 峰值采样为 1 秒粒度，可能低估瞬时峰值；未记录 nvidia-smi 功耗/温度。
6. 未新增 4x / SeedVR2 / 新工作流 / 新模型。

---

## 7. 交付状态

| 项 | 结果 |
|---|---|
| 功能提交 | `645649d` |
| 证据/放行提交 | `cb946eb` |
| GitHub CI（`645649d`） | `41789128325` success |
| GitHub CI（`cb946eb`） | `42238564650` success |
| GitHub CI（`91d8f5e`） | `42239189518` success |
| 放行状态（现场 API） | 四模块 `ready_to_run=true`、`default_profile_verified=true` |
| 验收包 | `D:\AIHome_2.0_L1_L2\archive\NSFW_Studio_W4.1_Review_Package.zip`（6.09 MB，72 文件） |

已完成：Gate 0、Gate 1、四个中心代码、0023、Hash 兼容、历史迁移、G3/G4、前端与 CI、验收包。
**本阶段到此停止，不进入 W4.2。**
