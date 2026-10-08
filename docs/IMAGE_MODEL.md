# IMAGE_MODEL — Image / Gallery 数据模型与流程（Phase 2C + Phase 3 + Phase 4，v0.5.0）

> 更新：2026-10-08。实现：`backend/app/models/image.py`、`backend/app/services/image_service.py`、
> `backend/app/api/v1/images.py`；迁移 `0006_image`（表）+ `0007_pipeline_stage`（Stage 关联）+
> `0009_execution_fingerprint`（StageItem.seed / binding_hash 历史修正）。
> 溯源与工作台恢复细则见 docs/PROVENANCE_SPEC.md；kind/parent/seed 判定见 docs/MODULE_IO_CONTRACT.md。

## 1. Image 表（0006_image）

| 列 | 类型 | 说明 |
| --- | --- | --- |
| id | TEXT PK | `img_<uuid4>` |
| job_id / job_item_id | TEXT FK | 来源 Job / Item（导入图片可为空） |
| parent_image_id | TEXT FK → images | 派生图溯源（Phase 3 起：高清图指向来源原图） |
| kind | TEXT | `original / upscaled / processed` |
| file_path | TEXT | **DataRoot 相对路径**（kind → 目录，见下） |
| width / height | INTEGER | 由 magic bytes 解析（PNG 头 / JPEG SOF） |
| seed | INTEGER | 该图实际 Seed（Phase 4 起来自 **StageItem.seed**；uses_seed=false 的 Stage 产出为 NULL） |
| review_status | TEXT | `UNREVIEWED（默认）/ KEPT / REJECTED` |
| favorite | INTEGER | 独立收藏位（0/1），与审核状态互不影响 |
| source | TEXT | `comfyui / mock / import` |
| metadata_json | TEXT | module/binding/workflow_hash/binding_hash + stage_id/stage_index/stage_item_id/parent 等溯源 |
| created_at / updated_at | TEXT | UTC ISO 8601 |

**kind → 存储目录（Phase 3 §十四）**：

```text
original  → images/originals/<img_id>/original.<ext>
upscaled  → images/upscaled/<img_id>/upscaled.<ext>   （parent_image_id = 来源原图）
processed → images/processed/<img_id>/processed.<ext> （预留）
```

## 2. 引擎输出导入流程（§三十九、§四十；Phase 2.2 §1 整批原子化；Phase 3 §十四）

```text
ComfyUI output（仅输出来源，绝非永久图库）——一个 StageItem 的输出 = 一个批次
  → prepare_image_output(data, kind=...)：全部输出先校验（任一不合法即整批失败）
  → 全部写入 Studio temp
  → 全部移动到 DataRoot/images/<kind 目录>/<img_id>/<kind>.<ext>
  → import_outputs_transaction()：单事务写入全部 Image（kind + parent_image_id + 元数据）→ commit
```

- kind / parent / seed 判定（`import_adapter_outputs`，Phase 4 Task2/3）：
  **全部来自当前 Stage 模块的 ModuleCapabilities**（`output_kind` / `parent_policy` /
  `StageItem.seed`），禁止再用"有 input_image_id 就推断为 upscaled"（见 docs/MODULE_IO_CONTRACT.md）；
- 任一步失败（校验 / temp / 移动 / 入库）：回滚 DB + 删除本批次已创建的全部正式文件 +
  清理 temp——**不会出现"半成功图库资产"**；Item 标 `STORAGE_ERROR` / `OUTPUT_MISSING`；
- 导入完成后 Worker 写回 `JobStageItem.output_image_id`（与 JobItem.image_id），
  最后 Stage 完成时记录 ITEM_COMPLETED（含 image_ids）。

## 3. Gallery API（§四十四；Phase 3 §十九/§二十四）

```text
GET   /api/v1/images                 过滤：job_id / review_status / favorite / source /
                                     kind / date_from / date_to / limit / offset
GET   /api/v1/images/{id}            详情
GET   /api/v1/images/{id}/content    文件流（缺失 → 404 IMAGE_FILE_MISSING）
GET   /api/v1/images/{id}/versions   父子关系：{image, parent, children}（§十九 原图 ↔ 高清切换）
PATCH /api/v1/images/{id}/review     保留 / 淘汰 / 未审核
PATCH /api/v1/images/{id}/favorite   收藏切换
GET   /api/v1/images/{id}/workbench  Image → 工作台快照 + 根图 Seed（Task7/9，见 §4）
GET   /api/v1/images/{id}/provenance Provenance：来源任务/Stage/模块/双指纹/Seed（Task10）
POST  /api/v1/images/upscale         §二十四：图库已有图片（1..N 张）→ 创建 upscale-only
                                     process Job（同一 QueueWorker 执行，绝不直连 ComfyUI）
GET   /api/v1/images/by-job/{id}/summary  按 Job 统计（total/未审核/保留/收藏/淘汰）
```

## 4. Image → Workbench（§四十七；Phase 4 Task7/9 追溯根生成 Job）

- 复用 Phase 1 `WorkbenchSnapshot`，不建立第二套恢复结构；
- 任何派生图（原图 / 高清 / 未来处理图）都沿 `parent_image_id` 追溯到**根生成图的 generate Job**，
  返回该 Job 当时的 workbench_snapshot——禁止恢复 process Job（图库高清）的空 Prompt；
- 外部导入图（无生成 Job）→ `404 IMAGE_NO_GENERATION_CONTEXT`（"没有可恢复的生成配置"）；
- Seed：默认 `random`（快照归一）；返回**根图 Seed** 供前端"使用原图 Seed"
  （置 `seed_mode=fixed`、**`count=1`**，§0.4 单张精确复现）；
- `workflow_modules` 携带**完整执行身份**（module/version/provider/binding_version/双指纹，Task9），
  提交时固定原版本执行；
- 细则见 docs/PROVENANCE_SPEC.md。

## 5. 从图库创建素材（§四十八）

- 素材创建支持 `source_image_id` 表单字段（POST /api/v1/assets）；
- Studio 为素材创建**独立资产文件**（图片字节复制到 `assets/<type>/<id>/v0001/`），
  同时 `assets.source_image_id` 记录溯源；
- 以后图库图片被清理，素材不受影响；
- 后端校验 source_image_id 对应 Image 必须存在（否则 404 IMAGE_NOT_FOUND）。

## 6. 图库 UI（§四十五、§四十六、§四十九）

- 顶部筛选：全部 / 未审核 / 保留 / 收藏 / 淘汰；"按任务查看"切换 Job 分组；
- Job 分组卡：`JOB-xxxxxxxx · N 张 · 未审核 a · 保留 b · 收藏 c · 淘汰 d`，点击进入该 Job 的图片；
- 图片 Grid（3:4 缩略图 + 审核/收藏角标）→ 点击打开右侧 Detail Drawer：
  大图、Prompt / Negative（来自 Job 快照）、Seed、Job ID、来源、时间、尺寸、审核状态；
- **溯源区（Phase 4 Task10）**：简洁展示"来源任务 / Seed / 管线（基础生成 → 高清 ×4）"，
  高级信息（来源原图 / Stage / 模块版本 / 引擎 Binding / 双指纹）折叠；
- Drawer 操作：保留 / 淘汰 / 取消审核 / 收藏 / 在生成工作台中打开 / 使用**原图** Seed / 创建素材 /
  高清放大。

## 7. 生成页联动（§五十）

中栏展示当前 Job 的"当前图 + 已完成缩略图"，图片生成一张立即显示一张
（SSE 通知 → 回源 GET → completed_count 变化触发刷新）；
续跑子 Job（resume_of_job_id）与父 Job 图片合并展示（§二十 父子归组）。

## 8. 验收对应

| 规范条目 | 验证 |
| --- | --- |
| §四十一-§四十三 模型 / kind / 审核 | tests/backend/test_image_service.py |
| §四十四 Gallery API | test_image_service.test_image_api_flow |
| §四十七 Image → Workbench（含 Seed） | test_image_api_flow + 前端 GalleryPage |
| Task7/9 派生图追溯根生成 Job + 完整身份 | test_phase4_history_provenance（含 process Job 追溯 / 导入图 404） |
| Task10 Provenance API | test_phase4_history_provenance.test_image_provenance_full_chain |
| Task2/3 kind/parent/seed 由能力判定 | test_phase4_contract |
| §四十九 按 Job 统计 | test_image_service.test_list_filters_and_job_summary |
| §五十九 真实生成入库 | tests/backend/test_comfyui_integration.py（1/3/8 张） |