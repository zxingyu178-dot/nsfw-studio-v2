# W3.1 客户端合同一致性报告

> 客户端基线：MediaReview `1212c30` 的
> `docs/integration/NSFW_MOBILE_API_CONTRACT_V2.md`、`NsfwStudioApi.kt`、`NsfwModels.kt`。
> 服务端基线：`e5ec120` + W3.1 主线整合。
> 结论：客户端冻结的 7 个 V2 端点与 5 项能力均已在 Bridge 实现，字段名/类型/错误码对齐；
> 未修改客户端仓库。

## 1. 端点对照

| 客户端 `NsfwStudioApi` | 服务端实现 | 状态 |
| --- | --- | --- |
| `GET /mobile/system/health` | `api/system.py` | 对齐 |
| `GET /mobile/images/feed` | `api/images.py::images_feed` | 对齐 |
| `GET /mobile/images/{id}/details` | `api/images.py::get_image_details_v2` | 对齐 |
| `POST /mobile/review/images/{id}/decision` | `api/review.py::image_decision` | 对齐 |
| `GET /mobile/prompts/{id}/review-summary` | `api/prompts.py::review_summary` | 对齐 |
| `GET /mobile/prompts/{id}/images` | `api/prompts.py::review_images` | 对齐 |
| `POST /mobile/prompts/{id}/evaluations` | `api/prompts.py::create_evaluation_v2` | 对齐 |
| `GET /mobile/prompts/evaluations/{client_request_id}` | `api/prompts.py::evaluation_receipt` | 对齐 |

配对与图片二进制（`/mobile/pairing/*`、`thumbnail/preview/original`）保持原 V1 实现。
冻结审核会话 `/mobile/review/sessions/*` 保持原行为。

## 2. DTO 字段对照

### 2.1 feed

客户端 `NsfwFeedItem` 字段：`image_id, revision, event, status, is_favorite, kind, job_id,
seed, width, height, created_at, updated_at, prompt{prompt_id,prompt_version_id,link_state},
thumbnail_url, preview_url, original_url`。
服务端 `mobile_v2_service.image_summary` 使用 `image_review_session_service._image_summary`
派生全部字段并附加 `prompt`，字段一致；`REMOVE` item 只返回 `image_id/revision/event`。

- `revision`：客户端要求十进制非负整数字符串，服务端已改为事件 `seq`；
- `event`：仅 `UPSERT` / `REMOVE`；
- `resumed`：空游标 false，否则 true；
- 首次同步包含历史图片（0022 回填）。

### 2.2 details

字段与 `NsfwImageDetails` 一致；`model / size_bytes / mime` 当前返回 `null`
（客户端均为 nullable，不影响展示）。`positive_prompt / negative_prompt` 仅 Job 快照；
导入图/无 Job 返回 `null`，不伪造。`link_state` 三态与客户端 `NsfwPromptLink` 一致。

### 2.3 decision

请求 `action? / favorite? / expected_updated_at / client_request_id` 与
`NsfwDecisionRequest` 一致；成功响应 `image_id/status/is_favorite/updated_at/revision`
与 `NsfwDecisionResult` 一致。favorite-only 保留原 status；409 `REVIEW_CONFLICT`
返回 `details.image` 权威状态。

### 2.4 prompt review / evaluation

- summary 字段与 `NsfwPromptSummary` 一致；`version_latest` / `prompt_latest` 分离，
  整体评分 `prompt_version_id=null`；
- images 字段与 `NsfwPromptImagesPage` 一致；缩略图统一 `/mobile/images/...`；
- evaluation 请求 `prompt_version_id? / overall_score / dimensions? / notes /
  client_request_id` 与 `NsfwEvaluationRequest` 一致；成功响应为
  `evaluation_id,prompt_id,prompt_version_id,overall_score,created_at,client_request_id`；
- receipt 响应与 `NsfwEvaluationReceipt` 一致，按设备隔离。

## 3. 能力与错误码

健康能力包含客户端要求的 5 项：

```
mobile_feed_v2 / mobile_image_details_v2 / mobile_image_decision_v2
/ mobile_prompt_review_v2 / mobile_prompt_evaluation_v2
```

错误码：

| code | HTTP | 服务端来源 |
| --- | --- | --- |
| `UNAUTHORIZED` / `DEVICE_REVOKED` | 401 | 配对鉴权；客户端可规范化为 AUTH_* |
| `CURSOR_EXPIRED` | 410 | feed / events 游标非法、未来或过旧 |
| `REVIEW_CONFLICT` | 409 | decision `expected_updated_at` 不一致 |
| `IDEMPOTENCY_CONFLICT` | 409 | 同 key 不同载荷 |
| `IMAGE_NOT_FOUND` | 404 | 图片不存在 |
| `PROMPT_VERSION_NOT_FOUND` | 404 | 版本不属于该 Prompt |
| `VALIDATION_ERROR` | 422 | 参数校验 / 图片分页游标 |
| `INTERNAL_ERROR` | 500 | 未处理异常 |

说明：客户端对无业务 code 的 404 在 `/mobile/prompts/*` 归一为 `PROMPT_NOT_FOUND`；
服务端版本错配使用 404 `PROMPT_VERSION_NOT_FOUND`，客户端会禁用该评分入口，
不会误判为 Bridge 缺能力。未返回 `PROMPT_UNLINKED` 独立 422：整体评分由客户端显式
`prompt_version_id=null` 表达；图片详情通过 `link_state=UNLINKED` 提供同一信息。

## 4. 已知差异 / 兼容说明

1. 客户端 `revision` 语义为事件 seq；W3.0 的 `expected_revision` / 详情 revision 已同步改为
   seq，旧 W3 测试已回归。
2. 服务端保留 W3.0 扩展端点（`/mobile/events`、`/mobile/sync/snapshot`、旧详情/审核/评分）；
   客户端 V2 不调用，不影响合同。
3. 旧分支游标（HMAC `seq.signature`）不被 `mr2_` 游标解析接受 → 410 并要求重新同步；
   客户端不持久化游标，符合合同。
4. 旧分支回执已合并；重放按旧指纹算法复核，不同载荷返回 409。
5. 客户端设备 `product` 前缀要求 `nsfw-studio`，服务端返回 `nsfw-studio`。
