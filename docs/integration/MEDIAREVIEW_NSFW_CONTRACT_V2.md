# MediaReview × NSFW Studio Mobile Review Bridge — Contract V2（W3.1 主线）

> NSFW Studio 基线：`e5ec120`（W3.0）→ W3.1 主线整合。
> 客户端事实源：MediaReview `1212c30` 的
> `docs/integration/NSFW_MOBILE_API_CONTRACT_V2.md`、`NsfwStudioApi.kt`、`NsfwModels.kt`。
> 本文件描述服务端已实现行为；契约冲突时以客户端冻结文件为准并记录在
> `docs/W3_1_CONTRACT_CONSISTENCY.md`。
> 机器可读：`openapi-mobile-review-v2.json`；样例：`fixtures/`。

## 1. 架构与安全边界（不变）

- Desktop Studio：`127.0.0.1:8000`，永远 loopback；手机不可达。
- ComfyUI：`8188`。
- Mobile Review Bridge：独立进程 `0.0.0.0:8877`，随 Studio 退出；**固定端口，禁自动换口**。
- 手机只访问 8877；不能启动生成、编辑 Prompt、永久删除图片。
- 配对码 6 位、一次性、10 分钟有效；Bearer Token 只存 SHA-256；吊销设备立即 401。
- 新接口全部经 `get_current_device`；开放端点只有 `/mobile/system/health` 与 `/mobile/pairing/*`。
- 图片二进制沿用 thumbnail / preview / original 既有缓存与 ETag。
- 冷启动健康等待上限 **120 秒**；启动探测只连 `127.0.0.1:8877`，不停止非本程序进程。

## 2. 统一 envelope

成功：

```json
{"success": true, "data": {...}, "error": null, "request_id": "..."}
```

失败：

```json
{"success": false, "data": null,
 "error": {"code": "CURSOR_EXPIRED", "message": "...", "details": {"snapshot_required": true}},
 "request_id": "..."}
```

旧 Bridge 401 码 `UNAUTHORIZED` / `DEVICE_REVOKED` 保留；客户端可规范化为
`AUTH_REQUIRED` / `AUTH_REVOKED`。

## 3. 健康与能力门禁

`GET /mobile/system/health`（开放）

```json
{"status": "ok", "product": "nsfw-studio", "version": "0.13.0", "api_contract": 2,
 "capabilities": [
   "image_review", "review_session", "favorite", "thumbnail", "preview", "original",
   "image_event_feed", "image_detail", "prompt_version_evaluation",
   "idempotent_mutation", "snapshot_resync",
   "mobile_feed_v2", "mobile_image_details_v2", "mobile_image_decision_v2",
   "mobile_prompt_review_v2", "mobile_prompt_evaluation_v2"
 ]}
```

客户端要求 `api_contract >= 2` 且包含最后 5 项能力；缺一即禁止配对与进入审核。
**绝不**包含 `permanent_delete` / `generation` / `engine_control` / `prompt_edit`。

fixture：`fixtures/health_v2.json`。

## 4. 增量图片 feed

### 4.1 `GET /mobile/images/feed?cursor=&limit=`

- `cursor`：服务端签发的不透明字符串；空/缺省 = 首次同步；客户端不解析。
- `limit`：1–100（客户端固定 50）。
- 响应 `data`：`items[]`、`next_cursor`、`has_more`、`resumed`。

`items[]`：

```json
{
  "image_id": "img_...", "revision": "17", "event": "UPSERT",
  "status": "NEW", "is_favorite": false, "kind": "original", "job_id": "job_...",
  "seed": 123, "width": 1024, "height": 1024,
  "created_at": "...", "updated_at": "...",
  "prompt": {"prompt_id": "prm_...", "prompt_version_id": "prmv_...", "link_state": "EXACT"},
  "thumbnail_url": "/mobile/images/img_.../thumbnail",
  "preview_url": "/mobile/images/img_.../preview",
  "original_url": "/mobile/images/img_.../original"
}
```

- `revision` 是数据库事件 `seq` 的十进制字符串（单调递增），**不是时间戳**。
- `event`：`UPSERT` 或 `REMOVE`；`REMOVE` 只表示从手机队列移除，不删除文件/审核记录。
- 同一 image_id 多条事件按 seq 依次下发；旧 revision 不得覆盖新状态。
- 空增量 `items=[]` 不代表删除；删除只由 `REMOVE` 表达。
- `has_more=true` 时用 `next_cursor` 继续；`has_more=false` 仍返回 `next_cursor`。
- 游标非法/未来/早于最早可用水位 → **HTTP 410 `CURSOR_EXPIRED`**，
  `details.snapshot_required=true`。
- 首次空游标同步包含全部历史图片（0022 为历史图片补首事件）。

## 5. 图片详情

`GET /mobile/images/{image_id}/details`

```json
{
  "image_id": "img_...", "created_at": "...", "generated_at": null,
  "width": 1024, "height": 1024,
  "positive_prompt": "生成时快照", "negative_prompt": "",
  "prompt_id": "prm_...", "prompt_version_id": "prmv_...", "link_state": "EXACT",
  "job_id": "job_...", "module_id": "basic_generate", "seed": 123,
  "model": null, "size_bytes": null, "mime": null,
  "updated_at": "...", "revision": "17"
}
```

- `positive_prompt / negative_prompt` 是生成时 Job 快照；外部导入或缺 Job → `null`。
- `link_state`：
  - `EXACT`：prompt + version 都经显式 ID 校验可靠；
  - `UNRESOLVED`：prompt 可靠、生成版本未知；
  - `UNLINKED`：无可靠 prompt（导入图不得伪造）。
- 关联仅来自 Job 快照 `source_prompt_id/version_id` 或 V1 导入元数据
  `v1_output.prompts[]`；**禁止按文本相同匹配**。
- 禁止返回 DataRoot / DB / workflow 文件路径 / 私有配置。

## 6. 单图审核

`POST /mobile/review/images/{image_id}/decision`

```json
{"action": "KEEP", "favorite": true,
 "expected_updated_at": "...", "client_request_id": "uuid"}
```

- `action` ∈ `KEEP / REJECT / RESET` 或 null；favorite-only 时只改收藏，**保留原 status**。
- `action` 与 `favorite` 不能同时缺失。
- `expected_updated_at` 与详情/feed 的 `updated_at` 对齐；不一致 → 409 `REVIEW_CONFLICT`，
  `details.image` 返回权威图片状态与最新 revision。
- 成功 `data`：`{image_id, status, is_favorite, updated_at, revision}`。
- `client_request_id` 幂等：同 ID 同载荷返回原结果；同 ID 不同载荷 → 409
  `IDEMPOTENCY_CONFLICT`。
- 审核只改状态，不删除文件；手机无永久删除入口。
- 写入使用 SQLite `BEGIN IMMEDIATE` 串行化；事务内重新校验设备有效性；
  业务状态 + 事件 + 回执同一事务提交。

## 7. 提示词审核汇总 / 图片

### 7.1 `GET /mobile/prompts/{prompt_id}/review-summary?version_id=`

```json
{
  "prompt_id": "prm_...", "prompt_version_id": "prmv_...",
  "link_state": "EXACT", "evaluation_count": 3,
  "version_latest": {"evaluation_id": "prev_...", "prompt_id": "prm_...",
                     "prompt_version_id": "prmv_...", "overall_score": 4,
                     "created_at": "...", "notes": ""},
  "prompt_latest": {"evaluation_id": "prev_...", "prompt_version_id": null, ...},
  "images_total": 12, "seen_count": 8, "keep_count": 6, "reject_count": 2,
  "has_new_samples": true
}
```

- 指定 `version_id` 时 `link_state=EXACT`，版本评分与整体评分分开：
  `version_latest` 只取该版本；`prompt_latest` 是跨版本最新。
- 未指定版本时 `link_state=UNRESOLVED`，`version_latest=null`；整体评分是显式选择。
- `seen_count` 只统计持久审核证据：`reviewed_at`、冻结会话 `seen`、设备级
  `mobile_image_seen`；图片进入 feed 不等于已阅。
- `has_new_samples`：该版本最新评分之后是否新增关联图片。

### 7.2 `GET /mobile/prompts/{prompt_id}/images?version_id=&cursor=&limit=`

```json
{"items": [{"image_id": "img_...", "thumbnail_url": "/mobile/images/img_.../thumbnail",
            "status": "KEEP", "is_current": false}],
 "total": 12, "current_index": 0, "next_cursor": "mpi_...", "has_more": false}
```

- 关联复用 `prompt_image_service`（Job 快照 + V1 导入元数据 UNION），不按文本匹配。
- 缩略图必须是 `/mobile/images/...`，不得暴露 Desktop `/api/v1/images`。
- `cursor` 绑定 `prompt_id + version_id`，跨对象复用 → 422 `VALIDATION_ERROR`。

## 8. 提示词评分

`POST /mobile/prompts/{prompt_id}/evaluations`

```json
{"prompt_version_id": "prmv_...", "overall_score": 4,
 "dimensions": {"subject": 4, "lighting": 3}, "notes": "...",
 "client_request_id": "uuid"}
```

- `overall_score` 必填整数 1..5；`dimensions` 可选，白名单
  `subject / clothing / scene / composition / lighting / style / quality`，每维 1..5；
  **缺失不补默认分**。
- `prompt_version_id` 可 null（用户明确选择“提示词整体评分”）；指定时校验版本属于该 Prompt，
  否则 404（客户端映射 `PROMPT_NOT_FOUND`，禁止评分）。
- `source` 固定 `mobile`；追加历史，不覆盖旧评分，不改 Prompt keep/candidate/eliminated。
- 评分 + `PROMPT_EVALUATED` 事件 + 幂等回执同一事务。
- 成功 `data`：`{evaluation_id, prompt_id, prompt_version_id, overall_score, created_at, client_request_id}`。
- 重放同 ID 同载荷返回原结果；不同载荷 → 409 `IDEMPOTENCY_CONFLICT`。

### 8.1 `GET /mobile/prompts/evaluations/{client_request_id}`

```json
{"found": true, "evaluation": {"evaluation_id": "prev_...", "prompt_id": "prm_...",
 "prompt_version_id": "prmv_...", "overall_score": 4, "created_at": "...",
 "client_request_id": "..."}}
```

- 按 `device_id` 隔离；其他设备查询同 request_id 返回 `{"found": false, "evaluation": null}`。
- 提交超时后客户端用同一 ID 查询；found=false 才允许重发。

## 9. 服务端扩展端点（非客户端冻结合同，保留兼容）

- `GET /mobile/events`：原始事件流（W3.0），同一 seq 游标；客户端 V2 使用 feed。
- `GET /mobile/sync/snapshot`：全量图片 + 水位 cursor，供首次/410 恢复。
- `GET /mobile/images/{image_id}`：W3.0 详情（含 prompt 名称/版本号/生成指纹）。
- `POST /mobile/images/{image_id}/review`：W3.0 单图审核（Header Idempotency-Key +
  expected_revision；revision 已统一为 seq）。
- `POST /mobile/prompts/{prompt_id}/versions/{version_id}/evaluation`：W3.0 版本评分。
- 冻结审核会话 `/mobile/review/sessions/*`、配对、图片二进制全部保持 V1 行为。

## 10. 数据与迁移

- `0021_mobile_event_log_mutations`：主干事件表 `mobile_image_events(seq,event_id,...)` +
  `mobile_mutation_receipts`；0021 改为 callable 守卫，识别参考分支旧结构。
- `0022_mobile_v2_compat`：旧分支 `(seq,image_id,event)` 原位扩展并保留原 `event` 审计列；
  历史图片补首事件；`mobile_write_receipts` 合并到主干回执；移除 images 触发器；
  建立 `mobile_image_seen`。幂等可重试，不删除设备/图片/Job/Prompt/评分。
- 唯一事件机制 = 业务服务显式写入；不允许服务写入与数据库触发器重复记录。
- 事件默认永久保留；若运维裁剪，早于最小水位的游标返回 410。
