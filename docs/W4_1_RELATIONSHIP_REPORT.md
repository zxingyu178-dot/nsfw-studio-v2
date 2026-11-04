# W4.1 Gate 0 — 关系与溯源报告

> 目标：证明现有数据能把 **图片 ↔ Prompt ↔ Job ↔ 工作流 ↔ 模型 ↔ Seed** 连接起来，
> 且历史派生关系（原图 → processed / upscaled）不被 W4.1 迁移破坏。
> 数据来源：`studio.db` 只读查询 + 全量文件清单 CSV。

---

## 1. 实体关系图（现状）

```text
Prompt 1 ─── n PromptVersion
  │                 │
  │                 └─ Job.workbench_snapshot_json.source_prompt_version_id（快照）
  │
  └─ Job.workbench_snapshot_json.source_prompt_id
       │
       └─ Job 1 ─── n JobItem（每项 Seed）
                 ├── n JobStage（module/provider/binding/workflow_hash/binding_hash）
                 │       └── n JobStageItem（input_image_id / output_image_id / seed）
                 └── n Image（job_id / job_item_id / seed / kind）
                          ├── parent_image_id（派生图 → 原图）
                          └── n ImageVariant（thumbnail / preview 缓存）

Image.metadata_json.v1_output.prompts ← 旧 V1 导入图片的 Prompt 归属（第二通道）
```

---

## 2. 关键关系计数

| 关系 | 数量 | 完整性 |
|---|---:|---|
| Prompt → PromptVersion | 294 → 294 | 每 Prompt 恰好 1 个版本 |
| Prompt → 图片（Job 快照通道 + 导入元数据通道） | 2,736 条链接 / 254 个 Prompt | 0 个无效 Prompt 引用 |
| Job → Image | 4,524 | 全部生成图有 `job_id` |
| JobItem → Image | 4,524 | 全部生成图有 `job_item_id` |
| JobStageItem → output Image | 4,525 | 生成图 4,524 + 1 条历史重复输出关系 |
| JobStageItem → input Image | 34 | 图生图/参考图链输入 |
| Image → parent Image | 32 | 父记录全部存在，无环 |
| Image → ImageVariant | 10,613 | 全部文件存在 |
| 导入图片 → Prompt（metadata） | 3,209 张导入图中的一部分 | 2736 总链接中大部分来自导入 |
| Job → workflow_hash | 946 | 无 NULL |
| Job → binding_hash | 946 | 无 NULL |

### 2.1 派生图关系

| kind | 数量 | 有父图 | 说明 |
|---|---:|---:|---|
| `original` | 7,706 | 5 | 5 张历史导入/处理图存在父关系，需在迁移中保留 |
| `processed` | 12 | 12 | 图片处理 Job 产物 |
| `upscaled` | 15 | 15 | 4x 已下线，历史兼容 |
| 合计 | 7,733 | 32 | 32/32 父图存在 |

---

## 3. 溯源链示例（真实记录）

### 3.1 新默认 Binding 的 G3 链（W4.0）

| 模块 | Job | 绑定 Hash | 输出图片 | Seed 记录位置 |
|---|---|---|---|---|
| basic v2 | `job_5fae2698-45c0-40a2-bfb8-9b25ba3e1dca` | `e34bf33b8451ec81` | `img_1488807d-...` | `job_items.seed` / `job_stage_items.seed` |
| anime v2 | `job_0f43ce4e-e143-4079-bce3-06f9b7f6c77d` | `a0aa56fb921178b0` | `img_15ae8248-...` | 同上 |
| img2img v3 | `job_40e4081b-377a-44ba-a2f3-3827d9d77b88` | `8ed91f6860c51cb4` | `img_0897edfa-...` | 同上 |
| reference v2 | `job_44dd171f-f91d-4cee-8e62-f94f1bf04755` | `4ac3b58b16203412` | `img_ccbedfec-...` | 同上 |

这些链均能通过 `Image.job_id → Job.workflow_hash/binding_hash` 回到执行身份；
`Image.parent_image_id` 保留输入链（basic → img2img → reference）。

### 3.2 历史 Prompt 链

- 294 个 Prompt 全部有 `current_version_id`；
- 图片关联通过两种证据：
  1. 新 Job：`workbench_snapshot_json.source_prompt_id` / `source_prompt_version_id`；
  2. 导入图：`metadata_json.v1_output.prompts[].prompt_id` / `version_id`；
- 两种通道 UNION 去重后得到 2,736 条图片链接，254 个 Prompt 有关联图片，40 个没有；
- 没有把“卡片前三张预览”当作全量数据：现有 `list_prompt_images` 独立分页。

### 3.3 手机审核链

- `mobile_review_sessions` 5 个、`mobile_review_session_items` 5,389 条，全部指向有效图片；
- `mobile_image_events` 8,006 条（创建 7,735 / 更新 269 / 删除 2），`seq` 全局单调；
- `mobile_mutation_receipts` 54 条幂等回执；旧 `mobile_write_receipts` 54 条保留；
- 手机端读取的是同一份 `images` 数据，不另建第二套资产。

---

## 4. 溯源缺口与解释

| 缺口 | 事实 | 处理原则 |
|---|---|---|
| Job 无 `model_snapshot` | 只有 1 个 Job 的 workflow snapshot 含 model 文本 | 新 Job 写入模型快照；历史 Job 用 Manifest 历史 + binding_hash 解释，不伪造 |
| 仅 32/946 Job 有真实 `source_prompt_id` | 其余为导入/旧流程 | 保留空值；导入图用 metadata 关联；不强行关联 |
| 4,524 张生成图无 `sha256` | 库内 NULL | 迁移逐张计算并回填，不伪造 |
| 2,146 个 JobItem 无 Seed | 多为取消/失败任务项 | 保留 NULL，不补造 Seed |
| `images` 无 `prompt_id` / `workflow_id` 列 | 关系在 Job 侧 | API 统一投影，不新增重复关系表 |
| 13 个 INTERRUPTED Job | 依赖归档模型，无法续跑 | 保留 Job/Stage/图片，标记不可恢复 |

---

## 5. W4.1 迁移后必须保持的关系

1. 所有 `images.file_path` 更新为新 `assets/images/...` 后，`Image.id` 不变；
2. `parent_image_id` 不变，派生图仍指向同一父图；
3. `image_variants.image_id` 不变，仅 `path` 改为 `cache/...`；
4. Job / JobItem / JobStage / JobStageItem 一行不删、不改身份字段；
5. Prompt / PromptVersion 一行不删、不改文本；
6. `mobile_image_events.seq` 与事件数量不减少；
7. `mobile_review_session_items` 与 `mobile_image_seen` 不改；
8. 图片总数、kind 分布、来源分布、审核状态分布迁移前后一致。

验收查询（迁移前后对比）：

```sql
SELECT kind, source, status, count(*) FROM images GROUP BY kind, source, status;
SELECT variant_type, count(*) FROM image_variants GROUP BY variant_type;
SELECT count(*) FROM prompts; SELECT count(*) FROM prompt_versions;
SELECT count(*) FROM jobs; SELECT count(*) FROM job_items; SELECT count(*) FROM job_stages;
SELECT count(*) FROM mobile_image_events; SELECT max(seq) FROM mobile_image_events;
SELECT count(*) FROM images WHERE parent_image_id IS NOT NULL;
```
