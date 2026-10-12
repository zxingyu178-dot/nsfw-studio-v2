# Phase 0.11 API 变更说明（API_CHANGE）

> 所有接口位于 `/api/v1` 前缀下。本阶段**只新增 / 扩展，不破坏任何现有 API**。
> 统一信封：错误为 `{"error": {"code", "message"}}`；列表为分页对象。

## 新增 / 变更接口

| # | 方法 | 路径 | 说明 |
|---|---|---|---|
| 1 | GET | `/images` | **标准分页**（page/page_size/sort/status），返回 `{items,total,page,page_size,has_next}` |
| 2 | GET | `/images/{image_id}/thumbnail` | 512px WebP q80；缺失按需生成并落 ImageVariant |
| 3 | PATCH | `/images/{image_id}/status` | 设置审核状态 `{status, note?}` |
| 4 | POST | `/images/batch-status` | 批量审核 `{image_ids,status,note?}` |
| 5 | POST | `/images/cleanup-rejected` | 两阶段废片清理（预览 / 真删，引用保护） |
| 6 | GET | `/images/by-job/{job_id}/summary` | 按 Job 审核统计 |
| — | POST | `/assets` | **复用**：图片→素材（已支持 `source_image_id`） |
| — | PUT | `/prompts/{id}/preview-image` | **复用**：设为 Prompt 封面 |

---

## 1. GET /images — 标准分页

### 查询参数
| 参数 | 默认 | 取值 / 约束 |
|---|---|---|
| `page` | 1 | ≥1 |
| `page_size` | 40 | 1~100 |
| `sort` | `created_desc` | `created_desc / created_asc / favorite / size` |
| `status` | 无 | `NEW/KEEP/FAVORITE/REJECT/ARCHIVED` |
| 既有过滤 | — | `job_id / review_status / favorite / source / kind / search / date_from / date_to` 保留 |

**旧调用方兼容**：保留 `limit`（≤200）/ `offset`（include_in_schema=false）。一旦提供 `limit`
即以其为页大小、走旧语义；ImagePickerDrawer / ResultPane 等 `limit=200` 调用方不受影响。

### 响应
```json
{ "items": [ImageResponse...], "total": 1000, "page": 1, "page_size": 40, "has_next": true }
```
排序说明：`size` 按像素数（width×height）倒序（图片无文件字节列，确定性可排序）。

## 2. GET /images/{image_id}/thumbnail
- 返回 `image/webp`，长边 512、quality 80。
- 缩略图缺失时**按需轻量 resize 生成**并写 `image_variants(thumbnail)`；历史图片不阻塞浏览。
- 原图损坏 / 解码失败 → `THUMBNAIL_FAILED`（400）。
- 另有服务端 `backfill_missing_thumbnails`（单张失败跳过）用于批量回填。

## 3. PATCH /images/{image_id}/status
- Body：`{ "status": "KEEP", "note"?: string }`。
- 除 `NEW` 外置 `reviewed_at`；`FAVORITE` 同步旧 `favorite=1`。
- **双写旧 `review_status`**：NEW→UNREVIEWED、KEEP/FAVORITE/ARCHIVED→KEPT、REJECT→REJECTED。
- 返回更新后的 ImageResponse。

## 4. POST /images/batch-status
- Body：`{ "image_ids": [...], "status": "REJECT", "note"?: string }`。
- 响应：`{ "updated": n, "items": [ImageResponse...] }`，单张失败不阻断其余。

## 5. POST /images/cleanup-rejected
- Body：`{ "image_ids"?: [...], "confirm": false }`。
- **confirm != true（预览）**：
```json
{ "candidate_count": 100, "total_bytes": 907144, "protected_count": 2 }
```
- **confirm=true（真删）**：
```json
{ "deleted_count": 98, "deleted_bytes": 907144, "protected_count": 2, "failed": [] }
```
- 删除前**逐张复用 ImageReferenceService.count_references**：被 Prompt / Asset / Recipe / 派生图 /
  活跃 Job 引用（total>0）的图跳过计入 protected，绝不留悬空。
- 真删内容：original + 全部 variants 文件（含 thumbnail）+ image_variants 行 + Image 行，
  并清空 `job_items.image_id / job_stage_items.output_image_id`；按外键依赖顺序显式删除；
  删除 now-empty 的 per-image 目录（仅当目录名即图 id 且为空）。

## 6. GET /images/by-job/{job_id}/summary
```json
{ "job_id": "job_demo", "total": 16, "unreviewed": 16, "kept": 0, "rejected": 0, "favorites": 0 }
```
按旧 `review_status` 聚合（故 PATCH 需双写）。

## 复用接口（未改动契约）
- **POST /assets**（multipart）：字段 `name / type / prompt_text / source_image_id / preview`，
  图片详情"创建素材"调用，素材为独立资产文件，图片以后被清理不影响素材。
- **PUT /prompts/{id}/preview-image**：body `{image_id}`，图片详情"设为 Prompt 封面"调用，
  封面属 Prompt 元数据、不产生 PromptVersion。
