# MediaReview × NSFW Studio Mobile Review Bridge — Contract V2

> 基线：NSFW Studio V2 `5a9df4a`（W2.0）→ W3.0。
> 适用端：MediaReview Android（独立仓库）通过局域网访问 **8767 Mobile Review Bridge**。
> 契约文件：本文 + `openapi-mobile-review-v2.json` + `fixtures/`。
> V1 契约（`MEDIAREVIEW_NSFW_CONTRACT_V1.md` / `openapi-mobile-review.json`）继续兼容，不删除。

## 1. 架构与安全边界（不变）

- Desktop Studio：`127.0.0.1:8000`，永远 loopback；手机不可达。
- ComfyUI：`8188`。
- Mobile Review Bridge：独立进程 `0.0.0.0:8767`，随 Studio 退出。
- 手机只访问 8767；**不能**启动生成、编辑 Prompt、永久删除图片。
- 配对码：6 位、一次性、10 分钟有效；Bearer Token 只存 SHA-256；吊销设备立即失效。
- 所有新接口必须在 `Authorization: Bearer <token>` 下访问（`get_current_device`）；
  唯一开放端点是 `/mobile/system/health` 与 `/mobile/pairing/*`。
- 图片二进制仍为 thumbnail / preview / original 三条既有缓存 + ETag 链路。

## 2. 统一 envelope

所有 `/mobile/*` JSON 响应：

```json
{"success": true, "data": {...}, "error": null, "request_id": "..."}
```

失败：

```json
{"success": false, "data": null,
 "error": {"code": "CURSOR_EXPIRED", "message": "...", "details": {"snapshot_required": true}},
 "request_id": "..."}
```

## 3. 健康与能力

`GET /mobile/system/health`（开放）

- `api_contract = 2`（V2 全部能力实现且测试通过后才升级；V1 客户端可继续使用 V1 接口）。
- `capabilities`：`image_review`、`review_session`、`favorite`、`thumbnail`、`preview`、
  `original`、`image_event_feed`、`image_detail`、`prompt_version_evaluation`、
  `idempotent_mutation`、`snapshot_resync`。
- **绝不**包含 `permanent_delete` / `generation` / `engine_control` / `prompt_edit`。

fixture：`fixtures/health_v2.json`。

## 4. 增量事件流

### 4.1 `GET /mobile/events?cursor=...&limit=...`

- `cursor`：不透明字符串（base64url，前缀 `mr2_`），不得解析为数据库 seq；首次可省略。
- `limit`：1–200，默认 50。
- 响应：`events[]`、`next_cursor`、`has_more`、`server_time`。
- `events[]` 字段：`event_id`、`event_type`、`image_id`、`revision`、`payload`、`created_at`。
- 事件按全局 `seq` 升序；翻页使用 `seq > cursor`，**不漏、不重**。
- 事件类型：
  `IMAGE_CREATED`、`IMAGE_IMPORTED`、`IMAGE_REVIEW_UPDATED`、`IMAGE_FAVORITE_UPDATED`、
  `IMAGE_METADATA_UPDATED`、`IMAGE_REMOVED`、`PROMPT_EVALUATED`。
- 事件日志**不依赖 images 外键**：图片永久删除后 `IMAGE_REMOVED` 仍可读。
- `payload` 只含手机可见字段（无 `file_path` / DataRoot / 工作流路径 / 私有配置）。

fixture：`fixtures/events_page.json`。

### 4.2 游标过期

- 非法游标、未来游标、或早于最小可用水位 → HTTP **410**，
  `error.code = CURSOR_EXPIRED`，`error.details.snapshot_required = true`。
- 客户端收到 410 必须重新调用 `/mobile/sync/snapshot`，然后用返回的 `cursor` 继续增量。

### 4.3 事件保留策略

- V2 默认**永久保留**事件，不自动清理；因此正常运行时最小可用游标 = 第一条事件 seq - 1。
- 若运维显式裁剪事件（当前版本不提供自动裁剪），早于最小可用水位的游标按 410 过期处理，
  不会静默返回缺页数据。
- 客户端不得假设事件无限增长；应定期用 snapshot 重建本地状态。

## 5. 快照恢复

`GET /mobile/sync/snapshot`

- 返回 `images[]`（全部图片的审核/收藏/尺寸/来源/Seed/URL）、`image_count`、
  `cursor`（当前事件水位）、`server_time`。
- `cursor` 与 `images` 在同一 DB 读事务中生成：客户端从该 cursor 拉增量，
  **不存在快照与增量之间的空隙**。
- 首次配对或收到 410 时使用。

fixture：`fixtures/snapshot.json`。

## 6. 图片详情

`GET /mobile/images/{image_id}`

返回：`image_id / width / height / created_at / updated_at / revision / status / is_favorite /
kind / source / job_id / seed / generation_module / generation_metadata /
prompt_snapshot / negative_prompt / source_prompt_id / source_prompt_version_id /
prompt_name / prompt_version_no / thumbnail_url / preview_url / original_url`。

- 优先复用 `image_service.get_provenance()` 与 Job 快照。
- 外部导入图片没有 Job / Prompt → 相关字段明确为 `null`，不伪造关联。
- 禁止暴露 DataRoot 绝对路径、数据库路径、ComfyUI 工作流文件路径、私有配置。

fixture：`fixtures/image_detail.json`。

## 7. 单图片审核（V2 新增）

`POST /mobile/images/{image_id}/review`

Header：`Idempotency-Key`（必填，1–128 字符，同一设备同一操作内唯一）。

Body：

```json
{
  "action": "KEEP | REJECT | RESET | null",
  "favorite": true,
  "expected_revision": "<GET 详情返回的 revision>",
  "note": "可选审核备注"
}
```

- `action` 与 `favorite` 至少提供一个；两者相互独立。
- 乐观锁：`expected_revision` 与服务端当前 `revision` 不一致 → HTTP **409**
  `error.code = REVIEW_CONFLICT`，`error.details.image` 为服务端权威 Image DTO，
  `error.details.revision` 为最新 revision。
- 成功响应：`image`（权威 DTO）、`revision`、`idempotent_replay`。
- **不允许永久删除**；REJECT 只是审核状态，清理仍只能由 Desktop 执行。
- 原有 `/mobile/review/sessions/{id}/decision` 保持兼容，内部复用同一审核服务与同一事件写入。

幂等规则：

- 相同 `Idempotency-Key` + 相同 Payload → 返回原成功响应，`idempotent_replay=true`，
  不重复写事件；
- 相同 Key + 不同 Payload → HTTP **409** `IDEMPOTENCY_CONFLICT`。

fixture：`fixtures/image_review_response.json`。

## 8. Prompt Version 评分（V2 新增）

`POST /mobile/prompts/{prompt_id}/versions/{version_id}/evaluation`

Header：`Idempotency-Key`（必填）。

Body：

```json
{"overall_score": 4, "dimension_scores": {"style": 4, "composition": 3}, "notes": "..."}
```

- 必须验证 `version_id` 属于 `prompt_id`（否则 404）。
- 复用 `PromptEvaluation`；`source = "mobile"`。
- 评分**不会**自动修改 Prompt 的 KEEP / CANDIDATE / ELIMINATED 状态。
- 评分、`PROMPT_EVALUATED` 事件、幂等回执在同一事务提交；重放不重复。
- 查询：`GET /mobile/prompts/{prompt_id}/versions/{version_id}/evaluations`。

fixture：`fixtures/prompt_evaluation_response.json`。

## 9. 错误码（V2 新增）

| HTTP | code | 含义 |
| --- | --- | --- |
| 410 | `CURSOR_EXPIRED` | 游标非法/过期；`details.snapshot_required=true`，请走 snapshot |
| 409 | `REVIEW_CONFLICT` | `expected_revision` 过期；`details.image` 为权威图 |
| 409 | `IDEMPOTENCY_CONFLICT` | 同一 Idempotency-Key 使用了不同 Payload |
| 401 | `UNAUTHORIZED` / `MOBILE_DEVICE_REVOKED` | 未配对或设备已吊销 |

既有 V1 错误码（`REVIEW_ITEM_NOT_FOUND`、`IMAGE_NOT_FOUND` 等）不变。

## 10. 兼容性

- V1 端点（health、pairing、sessions、queue、decision、position、complete、
  thumbnail/preview/original）全部保留；旧客户端无需迁移。
- `api_contract` 从 1 → 2 只在新客户端识别后使用；V1 客户端可忽略新增字段。
- `revision` 新字段向后兼容：V1 客户端不读取即可。
