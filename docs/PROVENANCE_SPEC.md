# PROVENANCE_SPEC — 图片溯源与工作台恢复（Phase 4 / v0.5.0）

> Task 7/9/10：派生图 → 根生成配置的追溯规则、执行身份恢复、Image Provenance API。

## 1. 溯源链（parent 关系）

```
根生成图（original，来自 generate Job）
└─ 高清图（upscaled，parent_image_id = 原图）
   └─ 未来处理图（processed / img2img / reference …，parent_image_id = 输入图）
```

- `Image.parent_image_id` 由 Stage 模块能力决定（`parent_policy == input_image` 时落库，见 MODULE_IO_CONTRACT.md）；
- 图库高清（process Job）产出的高清图同样挂到来源图下，**不复制成新的"原图"**；
- 外部导入图无 parent、无 job。

## 2. 从派生图恢复工作台（Task 7）

`GET /api/v1/images/{id}/workbench` 的追溯规则（固定）：

```
当前 Image → 沿 parent_image_id 一直向上 → 根图 → 根图的 generate Job
→ 返回该 Job 的 WorkbenchSnapshot（+ 完整执行身份）
```

- 从原图 / 高清图 / 任意派生图点击"在生成工作台中打开"，**默认恢复根图的原始生成配置**；
- 禁止恢复 process Job（图库高清）的空 Prompt；
- 根图为外部导入（无 job / job_kind != generate）→ `404 IMAGE_NO_GENERATION_CONTEXT`
  （文案"没有可恢复的生成配置"），绝不伪造 Prompt；
- Seed：返回**根图 Seed**（前端"使用原图 Seed"按钮使用）；
  快照内 `seed_mode` 被归一为 `random`（默认随机；用户显式使用原图 Seed 时前端置 fixed + count=1）。

## 3. 执行身份恢复（Task 9）

恢复出的快照中 `workflow_modules` 携带**完整执行身份**（来自根 Job 的 workflow_snapshot）：

```json
{"module_id": "basic_generate", "module_version": "v1", "provider": "comfyui",
 "binding_version": "v1", "workflow_hash": "…", "binding_hash": "…"}
```

提交时后端 `resolve_workflow_modules` 的规则：

| 请求项形态 | 行为 |
| --- | --- |
| 只有 `module_id`（普通新建） | 解析当前默认版本（含真实双指纹） |
| 携带完整身份（从历史 / Image / 配方恢复） | **固定原身份**执行，绝不静默升级 |
| 完整身份但 provider ≠ 当前引擎 | 拒绝：`BINDING_IDENTITY_MISMATCH` |
| 完整身份但指纹不一致 | 拒绝：`WORKFLOW_HASH_MISMATCH` / `BINDING_HASH_MISMATCH` |
| 老 Job（binding_hash = null） | 兼容执行；comfyui 下采纳磁盘当前指纹 |

> 不允许"老图 → 打开工作台 → 使用原 Seed，却偷偷跑新版 Workflow"。

## 4. Image Provenance API（Task 10）

```
GET /api/v1/images/{id}/provenance
```

| 字段 | 说明 |
| --- | --- |
| `image_id / kind` | 图片身份 |
| `parent_image_id / root_image_id` | 直接来源 / 根生成图（计算字段，不入库） |
| `scale` | 相对来源图的倍率（如 4x-UltraSharp → 4；无父图或同尺寸为 null） |
| `job_id / job_item_id` | 产出该图的 Job / 槽位（导入图为 null） |
| `stage_id / stage_index / stage_item_id` | 产出该图的 Stage 执行记录（老图片回落 metadata） |
| `module_id / module_version / provider / binding_version` | 执行模块身份 |
| `workflow_hash / binding_hash` | 执行指纹（双指纹） |
| `seed` | 该图真实 Seed（高清等 uses_seed=false 的产出为 null） |

前端图库详情：默认简洁展示（来源任务 / Seed / 管线：`基础生成 → 高清 ×4`），
技术字段折叠在"高级信息"。

## 5. 数据准确性（Task 3 的历史修正）

- `0009_execution_fingerprint` 迁移把历史 basic Stage 的 `StageItem.seed` 从 JobItem 回填；
- 历史上 upscale Stage / upscale-only Job 的"假 Seed"（从未被高清模型使用）被清空：
  包括 `Image.seed`（高清图）与 `JobItem.seed`（process Job）；新数据由能力驱动天然正确。