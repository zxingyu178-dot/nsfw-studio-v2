# W4.1 Gate 0 — 资产盘点报告

> 项目：`nsfw-studio-v2` · 盘点日期：2026-11-04 · 基线：`9904e126a1fa182a8506285e0bf990308a575495`
> 方式：只读。SQLite 以 `mode=ro` 打开；文件系统仅扫描与计算 Hash，未移动、未删除、未改写任何正式资产。
> 数据源：`D:\NSFW-Studio-Data\database\studio.db`（123,330,560 bytes）、`images/`、`registry` 现状文件、`release_manifest.yaml`、W4.0 模型清单。

---

## 1. 结论摘要

| 维度 | 结果 |
|---|---|
| 活动模型 | 6 个，全部存在，路径与大小已复核 |
| 归档模型 | 24 个实体文件（1 个是清单 CSV），合计约 26.86 GB，位于 `archive\models-2026-11\` |
| 工作流版本 | 9 个现存版本（4 个活动 + 5 个冻结历史），另 1 个已归档的 `upscale/v1` |
| 工作流文件 | 9/9 同时具备 `workflow.json` + `binding.yaml`；无缺失 |
| 图片登记 | 7,733 条，`images` 表全部有对应文件；缺失 0 |
| 图片物理文件 | 18,346 个（原图/派生图/缩略图/预览），14.65 GB；数据库未登记孤立文件 0 |
| 缩略图/预览 | `image_variants` 10,613 条，缺失文件 0 |
| Prompt | 294 条，版本 294 条；无“无版本”Prompt；无多版本 Prompt |
| Job | 946 条；全部带 `workflow_hash` 与 `binding_hash`；无 QUEUED/PAUSED/RUNNING 遗留 |
| 图片 SHA256 | 仅 3,209 条导入图有库内 SHA256（3,209/3,209 校验一致）；4,524 条引擎生成图未存 SHA256 |
| 重复物理文件 | 11 组（全部是缩略图同内容、不同 Image），额外文件 11 个 |
| DataRoot 备份 | 数据库快照 `backups\studio-20261104-103427.db`；DataRoot 全量副本 `D:\NSFW-Studio-Data-Backup-20261104`（20,992 文件 / 14.487 GB，0 失败） |

**Gate 0 判定：通过。** 不存在缺失图片、孤立图片或损坏 Hash；历史执行身份可用数据库直接证明。正式迁移前必须先停止 Studio 与 ComfyUI。

---

## 2. 模型盘点

### 2.1 活动模型（6 个）

`W4.0` 六个活动模型继续作为 W4.1 的模型基线；本次已重新确认文件存在与字节大小。SHA256 来自 W4.0（2026-11-03）实测值。

| model_id（W4.1 建议） | 文件 | 类型 | 大小 (bytes) | SHA256 | 物理路径 | 活动引用 |
|---|---|---|---|---|---|---|
| `qwen_image_2_1` | `qwen-image-2.1-UC-Q4_0.gguf` | diffusion_model / gguf | 4,151,573,280 | `13f59f20656efc0aa385d03c1fcac1a9dc2ad6e5ccc0ea9bfe1d6ac636f2c5b9` | `C:\ComfyUI_models\diffusion_models\` | basic v2 / img2img v3 / reference v2 |
| `qwen3vl_8b_w4a8` | `qwen3vl_8b_w4a8.safetensors` | text_encoder | 6,312,105,364 | `7754425e55e7bea2bfde4dde59a4cc236cb44e5ee9c215ea66ef8d47012824eb` | `C:\ComfyUI_models\text_encoders\` | basic v2 / img2img v3 / reference v2 |
| `texture_fix_vae_qwen_image_2_1` | `texture_fix_vae_for_qwen_image_2.1_bf16.safetensors` | vae | 675,509,688 | `36f56608b02077a50a08ea3dbcdb88351298ceba49948f41f9f87186378e6908` | `C:\ComfyUI_models\vae\` | basic v2 / img2img v3 / reference v2 |
| `qwen_image_2_1_turbo8_lora` | `qwen_image_2.1_turbo8_lora.safetensors` | lora | 913,314,512 | `208dd43250e1e01467ba190572ae2e7107a7870ec1ff026bc65f791fa1e80e95` | `projects\comfyui\app\models\loras\` | basic v2 |
| `f23gg_nsfw_qwen21` | `f23gg_nsfw_qwen21.safetensors` | lora | 159,436,456 | `c29f503f3515877882fd6b10f6849c78a4f2337c09021f4bd4b93d060c311aea` | `projects\comfyui\app\models\loras\` | basic v2 |
| `miaomiao_harem_v14` | `miaomiaoHarem_v14.safetensors` | checkpoint | 6,938,042,912 | `e2039a9f785b1fc1c692d3d49a92c8c5694def0e78bd0bae2d0e8a738d65dd59` | `C:\ComfyUI_models\checkpoints\` | anime v2 |

### 2.2 历史/归档模型

`archive\models-2026-11\` 共 24 个模型文件（另 1 个 `archive_report.csv`）：
Anima 2.9B、SeedVR2 3B、SeedVR2 Distill 1.4B、SeedVR2 EMA VAE（pth / fp16）、`qwen_3_06b_base`、`qwen_image_vae`、`qwen_image_2.1_vae_bf16`、CLIP L/G、SDXL VAE ×2、`femaledVaginus` 及 11 个画布实验 LoRA 等。

- 这些文件的完整 `文件名 / 大小 / SHA256 / 原始路径 / 活动引用 / 历史引用 / 处理结果` 见
  `docs/W4_0_MODEL_INVENTORY.csv`，本阶段不重新迁移。
- 归档目录不在 ComfyUI 活动搜索路径：`extra_model_paths.yaml` 只声明 `C:/ComfyUI_models/`；另一个活动根是 `projects/comfyui/app/models`。
- 归档模型仍被历史 Job 引用（Anima、旧 Qwen VAE、`qwen_3_06b_base`），因此**不得删除**；只能保持归档状态。
- `femaledVaginus_v1.3.safetensors` 与 `qwen2_1-femaledVaginus-...` 字节相同（SHA256 相同），归档中保留两份文件名、共享同一内容；迁移判定以 SHA256 为准。

### 2.3 模型目录与搜索路径

| 路径 | 用途 | 是否活动 |
|---|---|---|
| `C:\ComfyUI_models\` | ComfyUI `base_path`（diffusion_models / vae / text_encoders / checkpoints） | 是 |
| `projects\comfyui\app\models\` | ComfyUI 内置 `models` 目录（loras / ultralytics） | 是 |
| `archive\models-2026-11\` | 归档 | 否（不在搜索路径） |
| `C:\AIHome_ModelCache\comfyui\` | W4.0 迁移后已清空 | 否 |

`app/models/ultralytics` 的 3 个人脸/手/人像检测模型不在 W4.0 归档清单内，也无活动 Binding 引用，本阶段保持原位不动。

---

## 3. 工作流盘点

### 3.1 活动与冻结版本

| module / binding | 状态 | workflow.json | binding.yaml | 目录位置 |
|---|---|---|---|---|
| `basic_generate/v2` | 活动（默认） | 存在 | 存在 | `workflows/providers/comfyui/basic_generate/v2/` |
| `anime_generate/v2` | 活动（默认） | 存在 | 存在 | 同上 |
| `img2img/v3` | 活动（默认） | 存在 | 存在 | 同上 |
| `reference_generate/v2` | 活动（默认） | 存在 | 存在 | 同上 |
| `basic_generate/v1` | 冻结 | 存在 | 存在 | 同上 |
| `anime_generate/v1` | 冻结 | 存在 | 存在 | 同上 |
| `img2img/v1` | 冻结 | 存在 | 存在 | 同上 |
| `img2img/v2` | 冻结 | 存在 | 存在 | 同上 |
| `reference_generate/v1` | 冻结 | 存在 | 存在 | 同上 |
| `upscale/v1` | 已下线归档 | 已移出活动目录 | 已移出活动目录 | `archive/workflows-2026-11/upscale-v1/` |

未发现：缺失文件、未注册目录、重复模块目录。

### 3.2 双指纹（原始字节 vs LF 规范化）

W4.1 的关键背景：开发树与部署树同一提交因 CRLF/LF 不同，**原始字节 Hash 不同**；LF 规范化后完全一致。

| module/binding | 原始字节 workflow_hash | 原始字节 binding_hash | LF 规范化 workflow_hash | LF 规范化 binding_hash | 部署树 G3 Job 记录值 |
|---|---|---|---|---|---|
| `basic_generate/v2` | dev `af870a6442432dfd` / app `9da86110a20db1ed` | dev `d9ca1eba6c482f57` / app `e34bf33b8451ec81` | `af870a6442432dfd` | `d9ca1eba6c482f57` | `9da86110a20db1ed` / `e34bf33b8451ec81` |
| `anime_generate/v2` | dev `db2bd841c260a434` / app `144a4b9f63e8dc67` | dev `7832e2b669aa1c44` / app `a0aa56fb921178b0` | `db2bd841c260a434` | `7832e2b669aa1c44` | `144a4b9f63e8dc67` / `a0aa56fb921178b0` |
| `img2img/v3` | dev `c94f28966da4db41` / app `d8fac1d3b2e9c627` | dev `21d056e2f9e7db77` / app `8ed91f6860c51cb4` | `c94f28966da4db41` | `21d056e2f9e7db77` | `d8fac1d3b2e9c627` / `8ed91f6860c51cb4` |
| `reference_generate/v2` | dev `88007850182aff4d` / app `65dbbd6ca22eb9e7` | dev `cfc68ee2f803c9ed` / app `4ac3b58b16203412` | `88007850182aff4d` | `cfc68ee2f803c9ed` | `65dbbd6ca22eb9e7` / `4ac3b58b16203412` |
| `basic_generate/v1` | dev/app `d2ed92e0f1b44d76` | `6c1a64481fc4802e` | `65bcf20b8974cc26` | `7b271def8d3dbf0e` | 历史 Job 使用原始值 |
| `anime_generate/v1` | dev/app `ea418968a418b271` | `dfa750836ac536eb` | `8639521567e79ecc` | `64ea1bcd697beffb` | 历史 Job 另有更早 raw 值 |
| `img2img/v1` | `7c11569529d4e653` | `2f2d5c06055c623a` | `92132d53229d9bea` | `ca978ab11e07ca4a` | 历史 Job 使用原始值 |
| `img2img/v2` | `9c7d1a1f1113391d` | `6cec17b26508726c` | `fab10a5356d0a4af` | `70d52c82bee41f84` | 历史 Job 使用原始值 |
| `reference_generate/v1` | dev `b9413c99c1f4ddeb` / app `0d816c324a8dbd71` | dev `1022da22e48721e6` / app `8a395f7b8f5a597b` | `b9413c99c1f4ddeb` | `1022da22e48721e6` | 历史 Job 使用原始值 |

结论：
1. LF 规范化 Hash 在两棵树完全一致，可作为 W4.1 起新 Job 的稳定身份；
2. 历史 Job 的原始字节 Hash 必须继续可验证，否则 946 条 Job 的恢复/溯源会失效；
3. `.gitattributes` 当前**不存在**，必须补；但补属性不会追溯修正历史 Job。

---

## 4. 图片资产盘点

### 4.1 数据库 vs 文件系统

| 项 | 数量 |
|---|---|
| `images` 表记录 | 7,733 |
| 数据库记录对应文件存在 | 7,733（缺失 0） |
| `kind=original` | 7,706 |
| `kind=processed` | 12 |
| `kind=upscaled` | 15（4x 已下线，历史兼容） |
| 来源 `comfyui` | 4,524 |
| 来源 `import` | 3,209 |
| 有 `parent_image_id` | 32 |
| 无 `job_id` | 3,209（全部为 import） |
| 有 `sha256` | 3,209（全部为 import；库内值与磁盘实测一致） |
| 无 `seed` | 3,224（导入图 + 少量历史记录） |

### 4.2 文件系统

| 目录 | 文件数 | 体积 |
|---|---|---|
| `images/originals` | 7,706 | 13.20 GB |
| `images/upscaled` | 15 | 224.99 MB |
| `images/processed` | 12 | 15.16 MB |
| `images/thumbnails` | 7,695 | 186.98 MB |
| `images/previews` | 2,918 | 366.80 MB |
| `images/temp` | 0 | 0 |
| 合计 | 18,346 | 14.65 GB |

- **孤立文件：0**（磁盘上每个文件都能在 `images` 或 `image_variants` 找到登记）。
- **缺失文件：0**（每条图片/变体记录都有实体）。
- **重复物理文件：11 组，额外 11 个文件**，全部是 `thumbnail.webp` 同内容不同 Image（缓存内容相同，不代表原图重复）；无原图重复。
- 全量文件级清单见 `docs/W4_1_FILE_INVENTORY.csv`（18,346 行，含路径、大小、SHA256、DB 归属、是否孤立）。

### 4.3 当前存储结构问题（W4.1 要解决）

现状仍是按 `kind` 分裂的顶层图库：

```text
DataRoot/images/
├── originals/<image_id>/original.ext
├── upscaled/<image_id>/upscaled.ext
├── processed/<image_id>/processed.ext
├── thumbnails/<image_id>/thumbnail.webp
└── previews/<image_id>/preview.webp
```

与 W4.1 统一 Asset Center 目标不一致：没有单一 `assets/images` 逻辑根、派生图与缓存没有统一 StorageManager 语义。迁移方案见 `W4_1_MIGRATION_RISK.md`。

---

## 5. Prompt 盘点

| 项 | 数量 |
|---|---|
| Prompt | 294 |
| PromptVersion | 294 |
| 无版本的 Prompt | 0 |
| 多版本 Prompt | 0 |
| 无 `current_version_id` | 0 |
| `current_version_id` 指向不存在版本 | 0 |
| 收藏 | 0 |
| 归档 | 2 |
| 状态 | `candidate` 293 / `eliminated` 1 |
| 评分记录 | 1 |
| 模式 | `full` 293 / `structured` 1 |
| 空正向文本 | 0 |
| 有图片关联的 Prompt | 254 |
| 无图片关联的 Prompt | 40 |
| 关联图片总数（与现有查询口径一致） | 2,736 |
| 关联到不存在 Prompt 的链接 | 0 |

`structured_json` 字段分布（196 条结构化 Prompt）：`style` / `face` / `clothing` / `pose` / `scene` / `composition` / `lighting` / `extra` 各 196；其中 98 条带 `_v1_migration` 标记。

**结论：**
- 全部 294 条 Prompt 都有版本，不需要伪造历史修改记录；
- W4.1 要求字段 `character / action / camera`，当前对应 `face / pose / composition`，迁移时做**只读映射**，保留原字段；
- 收藏为 0 是真实数据，不得伪造；
- 卡片预览与“全部图片”分页已存在（v0.37 `+N` 抽屉）；本阶段需验证真实总数与分页稳定性。

---

## 6. Job 与生成溯源盘点

| 项 | 数量 |
|---|---|
| Job | 946 |
| 状态 | COMPLETED 616 / CANCELLED 283 / FAILED 34 / INTERRUPTED 13 |
| QUEUED / PAUSED / RUNNING | 0 |
| JobItem | 6,720 |
| JobStage | 954 |
| JobStageItem | 6,735 |
| JobStageItem 有输出图 | 4,525 |
| JobStageItem 有输入图 | 34 |
| JobEvent | 328,958 |
| 全部 Job 有 `workflow_hash` / `binding_hash` | 是（NULL = 0） |
| 引擎生成图无 JobItem | 0 |

### 6.1 按模块/版本分组

| module | module_version | binding | workflow_hash | binding_hash | 状态分布 |
|---|---|---|---|---|---|
| `basic_generate` | v1 | v1 | `f45c54cbd48ab058` | `a7911ab7a6c1d1be` | COMPLETED 229 / CANCELLED 132 / FAILED 14 |
| `basic_generate` | v1 | v1 | `d2ed92e0f1b44d76` | `6c1a64481fc4802e` | COMPLETED 69 / CANCELLED 31 / FAILED 5 / INTERRUPTED 11 |
| `basic_generate` | v1 | v1 | `65bcf20b8974cc26` | `a7911ab7a6c1d1be` | COMPLETED 4 / CANCELLED 73 / FAILED 8 |
| `basic_generate` | v1 | v1 | `f45c54cbd48ab058` | `6c1a64481fc4802e` | COMPLETED 1 / FAILED 1 |
| `basic_generate` | v1 | **v2** | `9da86110a20db1ed` | `e34bf33b8451ec81` | COMPLETED 1 / FAILED 1 |
| `anime_generate` | v1 | v1 | `d490281903bcedfe` | `dfa750836ac536eb` | COMPLETED 291 / CANCELLED 46 / FAILED 3 / INTERRUPTED 1 |
| `anime_generate` | v1 | v1 | `ea418968a418b271` / `d148f046a6f92f78` | `dfa750836ac536eb` | COMPLETED 2 / INTERRUPTED 1 |
| `anime_generate` | v1 | **v2** | `144a4b9f63e8dc67` | `a0aa56fb921178b0` | COMPLETED 1 |
| `img2img` | v1 | v1 | `7c11569529d4e653` | `2f2d5c06055c623a` | COMPLETED 11 / FAILED 1 |
| `img2img` | v1 | v1 | `92132d53229d9bea` | `ca978ab11e07ca4a` | COMPLETED 1 |
| `img2img` | v1 | **v3** | `d8fac1d3b2e9c627` | `8ed91f6860c51cb4` | COMPLETED 1 |
| `reference_generate` | v1 | v1 | `b9413c99c1f4ddeb` | `1022da22e48721e6` | COMPLETED 1 |
| `reference_generate` | v1 | v1 | `0d816c324a8dbd71` | `8a395f7b8f5a597b` | COMPLETED 1 |
| `reference_generate` | v1 | **v2** | `65dbbd6ca22eb9e7` | `4ac3b58b16203412` | COMPLETED 1 |
| `upscale` | v1 | v1 | `8232a833dc049803` | `6a7a21944d428ef6` | COMPLETED 2 |

- `basic_generate/v2` 的 1 个 FAILED 是 W4.0 首次 G3 因 `mobile_image_events.event NOT NULL` 失败的尝试，不是模型/工作流失败；修复后 COMPLETED 1。
- 13 个 INTERRUPTED 全部为 `basic_generate/v1`（11）与 `anime_generate/v1`（2），依赖已归档模型/旧 Qwen VAE，确认不可续跑；Job 与相关图片全部保留。

### 6.2 溯源缺口

| 缺口 | 现状 | W4.1 处理 |
|---|---|---|
| Job 快照无模型身份 | 仅 1 个 Job 的 `workflow_snapshot_json` 含 model 文本 | 新 Job 写入 `model_snapshot`（model_id/version/file_sha256） |
| 只有 32/946 Job 有真实 `source_prompt_id` | 其余导入图靠 `metadata_json.v1_output.prompts` 关联 | 保留双通道，不伪造 |
| 4,524 张引擎图无 `images.sha256` | 库中为空 | 迁移时逐张计算并回填 SHA256 |
| 图片无 `prompt_id` 列 | 通过 Job 快照/导入元数据关联 | 保持现有关系，API 统一投影，不复制第二套关系表 |
| Prompt 版本与图片关联仅按当前快照 | 历史版本图片通过 `source_prompt_version_id` | 保留；无版本号的历史导入标记 `legacy_import` |

---

## 7. 与 W4.1 目标的差距清单

1. **Model Center**：尚无 `registry/models/*/model.yaml`，模型状态只存在于 W4.0 CSV 与 Binding。
2. **Workflow Center**：尚无统一 `registry/workflows/*/manifest.yaml`；`release_manifest.yaml` 只承担放行状态。
3. **Image Asset Center**：无 `AssetIngestService` 统一入口；存储仍是 `images/originals|upscaled|processed` 分裂结构；引擎生成图无 SHA256。
4. **Prompt Center**：数据齐全；缺统一 Manifest/Schema、统计 API 与 legacy 映射说明。
5. **统一 Hash**：无 `.gitattributes`；Hash 只用原始字节，CRLF/LF 跨树不一致。
6. **Migration 0023**：当前生产库 `mobile_image_events` 已是主干结构（无 legacy `event` 列），但旧库/旧分支仍可能存在旧结构；`0021_mobile_v2_events` 与 `0021_mobile_event_log_mutations` 双记录存在。
7. **Agent 提交标准**：`docs/WORKFLOW_SUBMISSION_STANDARD.md` 只覆盖工作流；缺模型/Prompt/Asset 提交模板与统一 Validator。

---

## 8. Gate 0 证据与限制

- 数据库快照：`D:\NSFW-Studio-Data\backups\studio-20261104-103427.db`（123,330,560 bytes，SQLite backup API）。
- DataRoot 全量副本：`D:\NSFW-Studio-Data-Backup-20261104`（排除 `logs/`、`cache/`、`*.tmp`）。
- 扫描证据：`temp/w41_gate0_stats.json`、`temp/w41_gate0_asset_scan.json`、`temp/w41_duplicate_files.json`、`temp/w41_file_hashes.json`。
- 限制：本报告未重新计算 24 个归档模型的 SHA256（沿用 W4.0 实测值）；未对 4,524 张引擎图逐一重新计算库外 SHA256（文件清单 CSV 已包含全量 SHA256）。正式迁移时以迁移脚本的逐文件校验为准。
