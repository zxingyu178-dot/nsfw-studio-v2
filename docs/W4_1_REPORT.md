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
| 后端全量 pytest | **进行中** |
| G3 / G4 | **未执行** |
| GitHub CI / Commit SHA | **未执行** |

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

## 5. 测试与验收（待补）

| 项目 | 结果 |
|---|---|
| 后端全量 pytest | 进行中 |
| 前端 build | 通过（15.35s） |
| 前端 vitest | 488 passed / 97 files |
| G0 静态校验 | 待跑 |
| Registry Validator | 0 error / 7 warning |
| G3 四工作流出图 | 未执行 |
| G4 性能 | 未执行 |
| 手机端回归 | 待全量测试 |
| GitHub CI | 未执行 |

---

## 6. 已知限制

1. 全量 pytest 尚未结束，不能声明全绿。
2. G3/G4 尚未执行，`default_profile_verified` 仍为 `false`。
3. 旧 `images/*` 目录未归档/未删除，目前与新资产并存。
4. 0023 尚未写入正式库 `migration` 记录（新代码启动时应用；当前结构为安全跳过）。
5. 历史 Job 缺 `model_snapshot`，Provenance 明确标记，不伪造。
6. 未新增 4x / SeedVR2 / 新工作流 / 新模型。

---

## 7. 后续执行顺序

1. 全量 pytest 通过；
2. Commit + Push + GitHub CI；
3. 部署树 `git pull` + 重构建，启动新代码（应用 0023）；
4. G3 四工作流真实出图；
5. G4 冷/热启动、GPU/RAM 峰值；
6. 手机端回归 + 真实 HTTP probe；
7. 更新 `release_manifest.yaml` 的 G4 证据；
8. 最终报告 + `NSFW_Studio_W4.1_Review_Package.zip`，然后停止。
