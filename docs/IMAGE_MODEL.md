# IMAGE_MODEL — Image / Gallery 数据模型与流程（Phase 2C，v0.3.0）

> 更新：2026-10-07。实现：`backend/app/models/image.py`、`backend/app/services/image_service.py`、
> `backend/app/api/v1/images.py`；迁移 `0006_image`。

## 1. Image 表（0006_image）

| 列 | 类型 | 说明 |
| --- | --- | --- |
| id | TEXT PK | `img_<uuid4>` |
| job_id / job_item_id | TEXT FK | 来源 Job / Item（导入图片可为空） |
| parent_image_id | TEXT FK → images | 派生图溯源（upscaled/processed，Phase 2 未产生） |
| kind | TEXT | `original / upscaled / processed`（Phase 2 只产生 original） |
| file_path | TEXT | **DataRoot 相对路径**：`images/originals/<img_id>/original.<ext>` |
| width / height | INTEGER | 由 magic bytes 解析（PNG 头 / JPEG SOF） |
| seed | INTEGER | 该图实际 Seed（来自 JobItem，原样保留） |
| review_status | TEXT | `UNREVIEWED（默认）/ KEPT / REJECTED` |
| favorite | INTEGER | 独立收藏位（0/1），与审核状态互不影响 |
| source | TEXT | `comfyui / mock / import` |
| metadata_json | TEXT | module/provider/binding/workflow_hash 等溯源 |
| created_at / updated_at | TEXT | UTC ISO 8601 |

## 2. 引擎输出导入流程（§三十九、§四十）

```text
ComfyUI output（仅输出来源，绝非永久图库）
  → Adapter /view 取回字节
  → Studio temp 写入 → 校验（magic bytes + 尺寸解析，失败即拒）
  → 原子移动 DataRoot/images/originals/<img_id>/original.png
  → 数据库登记（失败 → 回滚删除文件，不留孤儿资产）
```

- 任一环节失败：不会产生"半登记"图片；Item 标 `STORAGE_ERROR` / `OUTPUT_MISSING`；
- 导入完成后 Worker 写回 `JobItem.image_id` 并记录 ITEM_COMPLETED（含 image_ids）。

## 3. Gallery API（§四十四）

```text
GET   /api/v1/images                 过滤：job_id / review_status / favorite / source /
                                     kind / date_from / date_to / limit / offset
GET   /api/v1/images/{id}            详情
GET   /api/v1/images/{id}/content    文件流（缺失 → 404 IMAGE_FILE_MISSING）
PATCH /api/v1/images/{id}/review     保留 / 淘汰 / 未审核
PATCH /api/v1/images/{id}/favorite   收藏切换
GET   /api/v1/images/{id}/workbench  Image → 工作台快照 + 该图 Seed
GET   /api/v1/images/by-job/{id}/summary  按 Job 统计（total/未审核/保留/收藏/淘汰）
```

## 4. Image → Workbench（§四十七）

- 复用 Phase 1 `WorkbenchSnapshot`，不建立第二套恢复结构；
- `GET /images/{id}/workbench` 返回 **Job 当时的 workbench_snapshot**（老 Recipe / Prompt 修改不影响）；
- Seed 默认 `random`；前端"使用此图 Seed"把 `snapshot.seed = image.seed`、
  `seed_mode = fixed` 后再注入工作台；快照 schema 已含 `seed` 字段。

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
- Drawer 操作：保留 / 淘汰 / 取消审核 / 收藏 / 在生成工作台中打开 / 使用此图 Seed / 创建素材。

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
| §四十九 按 Job 统计 | test_image_service.test_list_filters_and_job_summary |
| §五十九 真实生成入库 | tests/backend/test_comfyui_integration.py（1/3/8 张） |