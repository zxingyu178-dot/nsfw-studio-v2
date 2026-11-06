# W4.1 — 验收报告（Unified Resource & Asset Architecture）

> 项目：`nsfw-studio-v2` · 日期：2026-11-06 · 基线：`9904e126a1fa182a8506285e0bf990308a575495`
> 验收范围：W4.1 规格 §0–§17；本文件只写实际执行过的验证，未执行项明确标注。
> 最终交付提交：`COMMIT_TBD` · GitHub CI：`CI_TBD`

---

## 1. 结论

W4.1 的四中心（Model / Workflow / Prompt / Image Asset）、统一 ID/版本/Manifest/Hash/存储/API/Agent 提交标准、
0023 Migration、历史资产迁移、生成溯源与 Gate 7 验收均已完成。

- 后端全量：**718 passed / 1 skipped，耗时 25:13，退出码 0**（`temp/pytest_w41_final.log`）；
- 后端最终定向（快照/Provenance 增量）：45 项通过；
- 前端：`tsc --noEmit` + Vite 构建通过；Vitest **488 passed / 97 files**；
- Registry：`checked=40 errors=0 warnings=7`（7 条均为历史冻结 Binding 依赖归档模型的预期兼容 warning）；
- G0：`checked=9 errors=0 warnings=12`（历史冻结 Binding 既有 warning）；
- 模型 SHA256：6/6 活动模型 `installed`，大小与 SHA256 全部一致；
- 四工作流 Preflight：全部 `READY`，每个声明模型 `sha256_verified=true`；
- 实时 Job：`job_f6de2b35-5e15-4ef2-af69-66a3ea1313f7` COMPLETED，快照含 `engine_version=0.37.0`、
  `model_snapshot=5`、`hash_algorithm=lf-normalized-v1`；
- 历史迁移：7,733 图 / 10,613 变体，0 缺失、0 Hash 不一致、活动存储根 0 孤立；
- 验收包：`archive\NSFW_Studio_W4.1_Review_Package.zip`。

---

## 2. Gate 逐项验收

| Gate | 要求 | 证据 | 结果 |
|---|---|---|---|
| Gate 0 | 只读盘点 + 五份文档 + 文件清单 + DataRoot 备份 | `W4_1_ASSET_INVENTORY.md`、`W4_1_DATABASE_INVENTORY.md`、`W4_1_FILE_INVENTORY.csv`（18,346 行）、`W4_1_RELATIONSHIP_REPORT.md`、`W4_1_MIGRATION_RISK.md`；DataRoot 副本 20,992 文件 / 14.487 GB | PASS |
| Gate 1 | 四类 Schema + 模型/工作流 Manifest + Agent 模板 | `registry/schemas/*.schema.json`、30 模型 Manifest、10 工作流 Manifest、`agent_submissions/templates/*`、`scripts/validate_registry.py` | PASS |
| Model Center | 单/多文件、依赖、多版本、Hash、安装/缺失/归档、兼容工作流查询 | `ModelRegistryService`；多版本布局与 `(model_id, version)` 判重；`GET /registry/models?workflow_id=` | PASS |
| Workflow Center | Manifest 全字段、双 Hash、放行状态、前端只读 | 4 活动 + 5 冻结 + 1 归档；`/modules` 的 `registry` 投影；前端无模型文件名硬编码 | PASS |
| §4.5 运行依赖 | Loader 解析、目录映射、存在性、大小、SHA256、未知 Loader=UNKNOWN、缺失不 READY | 实时四模块 Preflight `READY`；模型 `sha256_verified=true`；负例测试 `test_preflight_declared_model_size_mismatch_blocks` | PASS |
| §4.6 Hash | LF 规范化 + 历史 raw 兼容 + 双环境测试 + 历史 Job 不全部失效 | `resource_hash.py`、`load_binding` raw/LF 双接受、`test_binding_loads_with_lf_hash_in_crlf_environment` | PASS |
| Prompt Center | 既有 ORM、版本只增、legacy、tags/rating、图片关联分页、避免 N+1 | `prompt_center_service.py`、`GET /prompts/{id}/center`、`/prompts` 批量查询；`test_prompt_center_exposes_tags_and_rating` | PASS |
| Image Asset Center | 唯一 Ingest、资产类型、父子、统一存储、缓存、元数据、软删除、手机端禁物理删除 | `asset_ingest_service.py`、`assets/images/...`、`cache/...`、`image_asset_view`、无 DELETE 路由（405） | PASS |
| §7 统一生成快照 | job/workflow/binding/hash/model/prompt/parameters/seed/engine_version/output_asset_ids | Job 快照 + `/jobs/{id}/provenance` + `/images/{id}/provenance`；实时 Job 证据 | PASS |
| Gate 5 历史迁移 | 备份→dry-run→演练→复制+SHA256→DB 副本→验收→旧文件保留 | `w41_migration_report.json`、`w41_migration_verify.json`、`W4_1_IMAGE_MIGRATION.md`、`W4_1_MIGRATION_MAP.csv` | PASS |
| Gate 6 前端/API | 工作流来自 Registry、四工作流、参数动态、图库/Prompt 统一、手机同一资产 | `/modules` + `workbenchStore`；前端构建与 488 单测；手机 API 复用同一 `images` 表 | PASS |
| §11.1 0023 | 旧 `mobile_image_events` 重建、保事件/seq/索引、幂等、不改 0021/0022 | `mobile_event_repair.py`、`test_0023_rebuilds_legacy_event_table`、`test_0023_is_idempotent`；旧库/当前库/W4.0 副本演练 | PASS |
| §12 Agent 提交 | 目录约定、四类模板、标准/版本/校验三份文档、12 项检查 | `agent_submissions/`、`AGENT_SUBMISSION_STANDARD.md`、`RESOURCE_VERSIONING_STANDARD.md`、`REGISTRY_VALIDATION_GUIDE.md` | PASS |
| Gate 7 | 数据库/迁移/备份/统计/四工作流/性能/手机 | 见第 3–9 节 | PASS |

---

## 3. 后端测试

| 项 | 结果 |
|---|---|
| 收集 / 运行 | 718 passed, 1 skipped, 25:13，退出码 0 |
| W4.1 定向 | `test_w41_registry.py` 22 项通过 |
| Preflight 定向 | `test_runtime_preflight.py` 17 项通过（含新增 engine_version / provenance 断言） |
| 新增负例 | 重复模型版本拒绝、未知模型依赖拒绝、Hash 错误拒绝、历史版本重复注册拒绝、CRLF 环境 LF Hash 加载 |
| 新增资产/Prompt | 导入资产统一存储、无物理删除、缺失/孤立统计、tags/rating |

命令：`.venv\Scripts\python -m pytest -o addopts="" -q`

## 4. 前端

| 项 | 结果 |
|---|---|
| 类型检查 + 构建 | `npm run build` 通过（Vite 5.4.21，13.22s，394.68 kB JS / 115.79 kB CSS） |
| 单元测试 | `npm run test:ci`：97 files / 488 tests passed |
| 工作流来源 | 工作台模块来自 `/api/v1/modules`，无 `.gguf` / `.safetensors` 生产硬编码 |

## 5. G0 / Registry / G3 / G4

| 项 | 结果 |
|---|---|
| G0（`validate_workflows.py`） | `checked=9 errors=0 warnings=12`（历史冻结 Binding） |
| Registry（`validate_registry.py`） | `checked=40 errors=0 warnings=7`（历史归档依赖 warning） |
| G3 四工作流真实出图 | 4/4 COMPLETED（2026-11-04，见 `w41_g3_g4_results.json`） |
| G4 冷/热 + 峰值 | 8 冷/热 + 4 峰值 Job，全部 COMPLETED，0 OOM |
| 引擎冷启动 | 329.6s（ComfyUI 0.37.0，完全停止状态） |

G3 输出（历史证据保留）：

| 模块 | Job | 输出 | 冷启动耗时 |
|---|---|---|---|
| basic_generate/v2 | `job_bf7490c6-55b5-4e33-8b69-99ebf3a8d876` | `img_02917c97-...` 832×1216 | 670.7s |
| anime_generate/v2 | `job_2b2a8e90-9047-4759-8b5c-0adadb976a9f` | `img_8ba43ec8-...` 832×1216 | 130.5s |
| img2img/v3 | `job_5500fbc7-b5f5-47d3-9f26-a607cae02564` | `img_5fdf7923-...` 832×1216 | 423.0s |
| reference_generate/v2 | `job_3c77f1ff-f1e0-4b97-bc98-74dd95a9a2c5` | `img_edc3a55a-...` 640×928 | 685.0s |

G4 峰值：

| 模块 | 冷 | 热 | GPU 峰值 | RAM 峰值 |
|---|---:|---:|---:|---:|
| basic_generate/v2 | 670.7s | 82.7s | 5,903 MB | 16,268 MB |
| anime_generate/v2 | 130.5s | 36.4s | 5,428 MB | 15,808 MB |
| img2img/v3 | 423.0s | 101.1s | 5,488 MB | 16,156 MB |
| reference_generate/v2 | 685.0s | 119.2s | 5,486 MB | 16,265 MB |

## 6. 模型安装与 SHA256

`temp/w41_model_verify.json`（`verify_hash=true`，首次计算 130.73s，之后按 path+size+mtime 命中缓存）：

| model_id | 版本 | 状态 | 大小 | SHA256 |
|---|---|---|---|---|
| qwen_image_2_1 | 2.1.0 | installed | 一致 | 一致 |
| qwen3vl_8b_w4a8 | 1.0.0 | installed | 一致 | 一致 |
| texture_fix_vae_qwen_image_2_1 | 1.0.0 | installed | 一致 | 一致 |
| qwen_image_2_1_turbo8_lora | 1.0.0 | installed | 一致 | 一致 |
| f23gg_nsfw_qwen21 | 1.0.0 | installed | 一致 | 一致 |
| miaomiao_harem_v14 | 14.0.0 | installed | 一致 | 一致 |

实时四模块 Preflight（`temp/w41_preflight_four_gap.json`）全部 `READY`：
basic 5 个模型、anime 1 个、img2img 3 个、reference 3 个，`sha256_verified=true`。

## 7. 历史迁移

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
| 活动存储根孤立文件 | — | 0 |

- 迁移为 Copy + SHA256 比对，数据库路径按批事务更新；旧 `images/*` 目录保留为只读历史副本，
  由资产统计的 `legacy_retained_files/bytes` 单独计数，不混入孤立清单；
- 全量旧路径 → 新 `storage_key` 对照：`docs/W4_1_MIGRATION_MAP.csv`（18,346 行）。

## 8. 生产部署与实时验证

部署树 `projects\nsfw-studio-v2-app`（`deploy/app-instance`）已 fast-forward 到 `COMMIT_TBD`，
前端 dist 由 `scripts/deploy_app_dist.ps1` 构建同步；ControlHub lifecycle 重启 Studio 成功。

| 项 | 实测结果 |
|---|---|
| `/api/v1/health` | `{"status":"ok","version":"0.37.0"}` |
| `/api/v1/registry/validate` | `checked=40 errors=0 warnings=7` |
| 四模块 Preflight | `READY`，声明模型全部 `installed` + `sha256_verified=true` |
| 实时生成 | Job `job_f6de2b35-5e15-4ef2-af69-66a3ea1313f7` `COMPLETED`，seed=424243，768×768 |
| 输出资产 | `img_905e9fb5-aafd-4bfc-8028-aea113057e86` → `assets/images/2026/11/<id>/original.png` |
| Job 快照 | `engine_version=0.37.0`、`hash_algorithm=lf-normalized-v1`、`model_snapshot=5` |
| 图片溯源 | `workflow=basic_generate/v1`、`prompt=prm_a071bc00-...`、`model_snapshot=5`、`engine_version=0.37.0` |
| 资产统计 | `total=7,746`、`missing_files=0`、`thumbnails_missing=0`、`with_prompt=2,749`、`without_prompt=4,997` |

> 首次实时生成曾出现一次 `ENGINE_NETWORK`（ComfyUI `/history` 请求失败）；同条件重试成功，
> 判定为引擎模型加载期间的瞬态网络失败，已在验收记录中保留，不隐藏。

## 9. 手机端

- `tests/backend/test_mobile_*.py` 共 66 项测试全部通过，全部使用隔离临时 DataRoot；
- Mobile Review V2 合同、配对鉴权、增量事件、幂等回执、冲突处理、路由守卫均未改动；
- 图片资产与桌面端共用同一 `images` 表与 `storage_key`，手机端不提供物理删除路由；
- 运行态 Bridge 在本次最终重启后未自动启动（`mobile_review.enabled=false`），
  因此“Bridge 实时健康”标记为**未执行**；手机端验证依据为独立 DataRoot 的后端合同测试。

## 10. Git / CI

| 项 | 结果 |
|---|---|
| 交付提交 | `COMMIT_TBD` |
| 分支 | `main` 与 `develop` 同步 |
| GitHub CI | `CI_TBD` |

## 11. 已知限制

1. 冷启动耗时受机械盘模型加载影响（basic 670s / reference 685s），不代表稳态吞吐；
2. 旧 `images/*` 目录保留（约 14 GB），由资产统计单独标记，未删除、未移动；
3. 历史 Job 缺 `model_snapshot` / `engine_version` 时为 `null`，不伪造；
4. 峰值采样为 1 秒粒度，未记录功耗/温度；
5. 手机端 Bridge 实时健康在本次最终态未启动（配置关闭），合同测试与隔离 DataRoot 测试通过。

## 12. 交付物

- 架构：`W4_1_ARCHITECTURE.md` + `W4_1_ARCHITECTURE.svg`（四中心 / 存储 / DB / API / 数据流）；
- 标准：`AGENT_SUBMISSION_STANDARD.md`、`RESOURCE_VERSIONING_STANDARD.md`、`REGISTRY_VALIDATION_GUIDE.md`；
- Schema：`registry/schemas/{model,workflow,prompt,asset,submission}.schema.json`；
- 迁移：`W4_1_IMAGE_MIGRATION.md`、`W4_1_MIGRATION_MAP.csv`、`w41_migration_report.json`、`w41_migration_verify.json`；
- 验收包：`D:\AIHome_2.0_L1_L2\archive\NSFW_Studio_W4.1_Review_Package.zip`
  （报告、证据、Registry 定义、核心源码、0023 源码、Git 状态；不含模型二进制、全部图片或整个 DataRoot）。
