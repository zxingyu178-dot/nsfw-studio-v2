# API 变更说明（Phase 0.11.1 后端性能与导航）

> 面向交接。本文列本轮**新增/变更**的端点与字段；不改前端由后续 agent 处理。
> 基础路径前缀 `/api/v1`。

## 1. 新增端点

### GET `/images/{image_id}/preview`

返回该图的 preview rendition（`image/webp`）。

- 最长边 1536、WebP q85、仅下采样、保留 alpha；
- 缺失则按需并发安全生成并落 `image_variants`（variant_type=preview）；
- 状态码/缓存头与 `/images/{image_id}/thumbnail` 一致；`original` 缺失 → 404 `IMAGE_FILE_MISSING`。

### 历史回填

- `POST /images/thumbnails/backfill`
  - body：`{ "kind"?: "thumbnail" | "preview"（默认 thumbnail）, "limit"?: int(1..2000) }`；
  - 启动（或复用）一个后台回填任务，**立即返回状态**；同一时间只允许一个任务，
    重复调用返回当前任务、不重复起。
- `GET /images/thumbnails/backfill/status`
  - 返回 `{ running, done, total, failed, kind }`；
  - `total`=待处理总数、`done`=完成、`failed`=失败跳过数（单张失败不阻断）。
- `POST /images/thumbnails/backfill/stop`
  - 请求停止（置 flag，当前张完成后停止），返回最终状态。
- 不占 GPU；Studio 重启后再次调用可重算缺失（进程内状态，无持久化任务）。

### GET `/images/job-groups`（按任务聚合，避免 N+1）

- query：`page`（默认 1）、`page_size`（默认 20，1..100）；
- 只含 `status=COMPLETED` 且有产出图的 Job，按 Job `created_at` 倒序（`id` 兜底）；
- 返回：

```json
{
  "items": [
    {
      "job_id": "job_...",
      "module_id": "basic" | "upscale" | null,
      "created_at": "ISO8601",
      "total": 10,
      "unreviewed": 3,
      "kept": 5,
      "rejected": 2,
      "favorites": 1
    }
  ],
  "total": 12,
  "page": 1,
  "page_size": 20,
  "has_next": false
}
```

- 计数口径与 `GET /images/by-job/{job_id}/summary` **完全一致**：
  `unreviewed=NEW`、`rejected=REJECT`、`kept=KEEP+ARCHIVED`、`favorites=favorite=true`；
- 用单次 SQL `GROUP BY job_id`（favorites 用条件聚合），**取代前端"取最近 50 Job 再
  slice 20、逐 Job 发 summary"的 N+1 依赖**；可分页到早期 Job。

## 2. 变更行为（无签名破坏）

- **新图入库主动生成 thumbnail**：图片成功落库后 best-effort 基于内存字节生成 thumbnail；
  失败仅 warning，不影响落库。`GET /images/{id}/thumbnail` 多数情况下直接命中已有 variant。
- **分页稳定 tie-breaker**：`GET /images` 排序补 `id` 兜底——
  `created_desc=(created_at.desc, id.desc)`、`created_asc=(created_at.asc, id.asc)`；
  `favorite`/`size` 主排序键后补 `created_at.desc, id.desc`。连续页无重复/遗漏。

## 3. ImagePicker 历史可达契约（前端消费）

标准分页 + 过滤已可支撑选择器：

- 最近：`sort=created_desc`；待审核：`status=NEW`；保留：`status=KEEP`；
  收藏：`favorite=true`；
- `page/page_size` 可分页到最早一张（`has_next` 最终 false、无重漏）；
- 网格改用 `GET /images/{id}/thumbnail`，渐进/放大用 `/preview` 与 `/content`。

## 4. 未做项（边界）

- 未改 Engine/ComfyUI Runtime/Adapter、Queue Job State、PromptVersion、Recipe 快照、
  Lightbox 本体；
- 未新增 AI 能力/自动评分/自动标签；
- 未把 upscaled/processed 派生 Image 塞入 image_variants；
- 前端改动（Job 视图改用 job-groups、ImagePicker 改缩略图/分页）由后续 agent 完成。
