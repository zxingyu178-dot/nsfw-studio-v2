# NSFW 侧手机审核合同总览（Mobile Review Contract v1）

> 对端：NSFW Studio Mobile Review Bridge（Phase 0.13，独立端口 8767）。
> 本文件是 MediaReview Android 侧对接 NSFW 桥的**唯一合同事实源**。
> 所有路径 / 字段 / 状态码以冻结的
> `docs/integration/openapi-mobile-review.json` 与 `docs/integration/fixtures/*.json`
> 为准；后端实现见 `backend/app/mobile_main.py` 与 `backend/app/api/mobile/*`。
>
> 本文档只描述 **手机 → Bridge(8767)** 这一段。Desktop Studio(8000)
> 始终 loopback，手机不可直达；配对码由 Desktop 在本机 loopback 生成后展示给用户。

---

## 1. Base URL 与网络边界

- 协议：`http`（同网段局域网，不启用 TLS）。
- Base URL：`http://<lan-ip>:8767`
  - `<lan-ip>` 为运行 NSFW Studio 的电脑在手机可达网段上的 IPv4 地址。
  - 端口固定 **8767**（Bridge 独立进程，host `0.0.0.0`）。
- Desktop Studio 主进程端口 **8000 始终 loopback**，不向手机暴露；
  手机**永远不要**向 `:8000` 发任何请求。
- Bridge 是审核专用最小面：只 include
  `system / pairing / images / review` 四个子域；
  jobs / engine_runtime / prompts / recipes / assets / cleanup / modules /
  desktop SPA 一律不存在（route table 守卫测试断言）。
- CORS 放开（`allow_origins=*`），鉴权完全靠 Bearer，不靠 Origin。

---

## 2. 统一 Envelope（仅 JSON 响应）

除图片二进制流外，所有 `/mobile/*` JSON 响应统一为：

```json
{
  "success": true,
  "data": { },
  "error": null,
  "request_id": "uuid"
}
```

失败：

```json
{
  "success": false,
  "data": null,
  "error": { "code": "ERROR_CODE", "message": "…", "details": { } },
  "request_id": "uuid"
}
```

字段固定：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `success` | bool | 业务是否成功 |
| `data` | object \| null | 成功时为业务数据；失败时恒为 `null` |
| `error.code` | string \| null | 机器可读错误码；成功时 `null` |
| `error.message` | string \| null | 人读消息 |
| `error.details` | object \| null | 附加上下文（如 409 时的权威 Image） |
| `request_id` | string | 每次请求唯一 ID，响应头同时带 `X-Request-ID` |

HTTP 状态码与 `error.code` **同时存在**，客户端两层都要处理。
图片二进制端点（`image/webp`、`image/*`）**不包 envelope**，原样返回文件流。

---

## 3. 认证与配对（Bearer）

### 3.1 开放端点（无需 Bearer）

仅以下三个：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/mobile/system/health` | 健康 + 能力集 |
| GET | `/mobile/pairing/status` | 是否存在有效配对码（不下发码） |
| POST | `/mobile/pairing/verify` | 配对码换 Bearer token（一次性） |

其余所有端点（review / images / position / complete）必须带
`Authorization: Bearer <token>`，缺失或无效 → **401**。

### 3.2 配对码生命周期

- 配对码由 **Desktop loopback(8000)** 调用
  `POST /api/v1/mobile-review/pairing/code` 生成（手机侧**不调用**该端点），
  在 Desktop 界面展示给用户。
- 6 位纯数字、**一次性**、TTL **600 秒（10 分钟）**；成功核销即失效。
- 服务端只存 `SHA-256(code)`，不落明文。

### 3.3 换 token

`POST /mobile/pairing/verify`

请求体：

```json
{
  "installation_id": "device-fingerprint",
  "device_name": "Pixel",
  "code": "123456"
}
```

| 字段 | 约束 |
| --- | --- |
| `installation_id` | 必填，长度 1–128；首次生成后稳定，跨重新配对保留 |
| `device_name` | 可选，最长 128 |
| `code` | 必填，**恰好 6 位数字** |

成功 200（fixture `pairing_verify.json`）：

```json
{
  "success": true,
  "data": {
    "device_id": "mdev_abc123",
    "installation_id": "accept-phone-1",
    "name": "accept-client",
    "token": "d8a7f2c4e6b01359a2f4c6d8e013579b2468ace013579bdf2468ace013579",
    "paired_at": "2026-10-12T10:00:00.000Z"
  },
  "error": null,
  "request_id": "…"
}
```

- `token` 为 256-bit 随机数的 hex（64 字符），**仅此一次返回**；
  服务端之后只存其 `SHA-256`。
- 同一 `installation_id` 再次 verify：upsert 该设备、**轮换 token**、
  旧 token 立即失效、`revoked` 重置为 false。
- 失败 400：`error.code = "PAIRING_CODE_INVALID"`
  （码不对 / 已用过 / 已过期，三者同码，不区分）。

### 3.4 Bearer 鉴权失败语义

| HTTP | `error.code` | 含义 |
| --- | --- | --- |
| 401 | `UNAUTHORIZED` | 缺少 / scheme 错 / token 不存在或已吊销之外的无效（fixture `error_unauthorized.json`） |
| 401 | `DEVICE_REVOKED` | token 存在但设备已被吊销 |

收到 401 → 客户端应回到配对流程（清空本地 token，提示重新输入配对码）。

---

## 4. Health（开放）

`GET /mobile/system/health`（fixture `mobile_health.json`）：

```json
{
  "success": true,
  "data": {
    "status": "ok",
    "product": "nsfw-studio",
    "version": "0.13.0",
    "api_contract": 1,
    "capabilities": ["image_review", "review_session", "favorite", "thumbnail", "preview", "original"]
  },
  "error": null,
  "request_id": "…"
}
```

- `api_contract` 为整数，当前冻结值 **1**。
- `capabilities` 是固定白名单，**绝不包含**
  `permanent_delete / engine_control / generation / prompt_edit`
  （这些只存在于 Desktop 8000）。

### 兼容判定（Android 侧 gate）

1. 先打 `GET /mobile/system/health`；
2. 断言 `data.product == "nsfw-studio"` 且 `data.api_contract >= 1`；
3. 不满足 → 直接 `Incompatible`，**不再继续** pairing / queue / image 探测；
4. 满足后再走 `pairing/status` → 问用户要配对码 → `pairing/verify` 换 token。

> 注意：这是 **NSFW Bridge 自己的 gate（contract=1）**，
> 与 MediaReview Server 的 `SERVER_API_CONTRACT=2` 是两套独立合同，
> 不要混用阈值。

---

## 5. 冻结式 Review Session 端点（Bearer）

会话语义：创建时把符合 filter 的 image_id **顺序冻结**进队列；
之后图片在 NEW→KEEP/REJECT 之间流转**不改变队列成员与顺序**。

### 5.1 创建会话

`POST /mobile/review/sessions` → **201**

请求体（filter 可空，缺省即默认值）：

```json
{ "filter": { "status": "NEW", "sort": "created_desc" } }
```

- `filter.status`：默认 `NEW`。
- `filter.sort`：默认 `created_desc`；可选 `created_asc`
  （其余排序键本合同未开放）。

响应为 SessionSummary（fixture `review_session.json`）：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 会话 ID（如 `mrs_0001`） |
| `status` | string | `ACTIVE` / `COMPLETED` |
| `total_count` | int | 冻结队列总条数 |
| `seen_count` | int | 已审条数（服务端权威，客户端不得自行 +1） |
| `current_index` | int | 最近一次 `/position` 记录的浏览位置 |
| `created_at` / `updated_at` | string(ISO8601) |  |
| `filter` | object | 创建时冻结的 filter 快照 |

### 5.2 恢复最近会话（不重建）

`GET /mobile/review/sessions/latest` → **200** 或 **404**

- 200：返回 SessionSummary（同 5.1）。
- 404：`error.code = "REVIEW_SESSION_NOT_FOUND"`（尚无任何会话）。
- 恢复顺序：**先 `latest`，仅在明确 404 时才 `POST /sessions` 新建**；
  其它错误（401 / 5xx / IO）一律视为打开失败，**绝不"失败即新建"**。

### 5.3 分页取冻结队列（绝对 index 不压缩）

`GET /mobile/review/sessions/{session_id}/queue?page=1&page_size=50`

| 参数 | 约束 |
| --- | --- |
| `page` | int，默认 1，**从 1 开始**，≥1 |
| `page_size` | int，默认 50，范围 1–200 |

200（fixture `review_queue_page.json`）：

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "index": 0,
        "seen": false,
        "image": { /* MobileImageSummary，见 §6 */ }
      }
    ],
    "total": 3,
    "page": 1,
    "page_size": 50
  },
  "error": null,
  "request_id": "…"
}
```

- `items[].index` 为**冻结的绝对 index（0 基）**，服务端**永不压缩**：
  即使某图被 RESET 回 NEW 或被他处改动，该 index 位置仍保留对应图。
- 客户端定位本地 pager 位置必须用
  `items.indexOfFirst { it.index == targetIndex }`，
  **禁止**用 `targetIndex - baseIndex` 推算。

### 5.4 记录浏览位置（断点续看）

`POST /mobile/review/sessions/{session_id}/position`

```json
{ "item_index": 0 }
```

- `item_index` 必须 `≥0` 且 `< total_count`；越界 →
  422 `error.code = "POSITION_OUT_OF_RANGE"`。
- 返回 SessionSummary；只更新 `current_index`，**不改变 seen**。

### 5.5 标记完成（fail-closed）

`POST /mobile/review/sessions/{session_id}/complete`

- 仍有 `seen=false` 的条目时：**200** 返回
  `{ …SessionSummary, "completed": false, "remaining_count": <n> }`，
  不强制完成。
- 全部审完：200 返回 `{ …SessionSummary, "completed": true, "remaining_count": 0 }`，
  会话 `status` 置为 `COMPLETED`。

---

## 6. MobileImageSummary DTO（队列项 / decision 响应 / 409 权威图）

出现在 `queue.items[].image`、decision 响应的 `image`、409
`error.details.image` 三处，字段完全一致：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `image_id` | string | 图片 ID（如 `img_0001`） |
| `width` / `height` | int | 像素 |
| `created_at` / `updated_at` | string(ISO8601) | `updated_at` 是乐观锁版本戳 |
| `status` | string | `NEW` / `KEEP` / `REJECT` |
| `is_favorite` | bool | 收藏标志（独立于审核状态） |
| `kind` | string | 图片种类（如 `original`） |
| `job_id` | string \| null | 所属生成任务 |
| `seed` | int \| null | 生成种子 |
| `thumbnail_url` | string | 相对路径 `/mobile/images/{image_id}/thumbnail` |
| `preview_url` | string | 相对路径 `/mobile/images/{image_id}/preview` |
| `original_url` | string | 相对路径 `/mobile/images/{image_id}/original` |

- URL 均为**相对路径**，客户端拼 `http://<ip>:8767` 前缀。
- DTO **不下发** DataRoot / 绝对磁盘路径 / DB 路径 / workflow 路径。

---

## 7. 图片内容端点（Bearer，二进制流，不包 envelope）

| 方法 | 路径 | 档位 | Content-Type |
| --- | --- | --- | --- |
| GET | `/mobile/images/{image_id}/thumbnail` | 约 512 WebP | `image/webp` |
| GET | `/mobile/images/{image_id}/preview` | 约 1536 WebP（默认档位） | `image/webp` |
| GET | `/mobile/images/{image_id}/original` | 原图（仅放大/详情，谨慎） | `image/*`（按原文件 MIME） |

统一响应头：

```
ETag: "thumb-<image_id>-<w>x<h>-<updated_at>"     # preview/original 前缀分别为 preview-/orig-
Cache-Control: private, max-age=300
X-Content-Type-Options: nosniff
```

- 客户端应支持 `If-None-Match` 走 304；Coil 可直接复用 ETag 缓存。
- `original` 文件缺失 → 404 `error.code = "IMAGE_FILE_MISSING"`
  （注意：这是 JSON envelope，因为错误中间件把它包回 envelope）。
- 原图层仅在用户主动放大/查看详情时拉取，邻页只加载 preview/thumbnail，
  避免多张原图并发下载。

---

## 8. Decision（一次一事务）

`POST /mobile/review/sessions/{session_id}/decision`

请求体（openapi 示例）：

```json
{
  "item_index": 0,
  "action": "KEEP",
  "favorite": null,
  "expected_status": "NEW",
  "expected_updated_at": "2026-10-12T09:59:00.000Z"
}
```

| 字段 | 说明 |
| --- | --- |
| `item_index` | 与 `image_id` 二选一；优先用 `item_index`（冻结队列定位） |
| `image_id` | 备选定位方式 |
| `action` | `KEEP` / `REJECT` / `RESET`（见下） |
| `favorite` | `true` / `false` / `null`（不改）；**独立于 action** |
| `expected_status` | 乐观锁：提交前客户端看到的 `image.status` |
| `expected_updated_at` | 乐观锁：提交前客户端看到的 `image.updated_at` |

action 语义（同事务更新 Image + SessionItem.seen + Session.seen_count）：

| action | Image.status | 备注 |
| --- | --- | --- |
| `KEEP` | `KEEP` | `seen=true` |
| `REJECT` | `REJECT` | `seen=true` |
| `RESET` | `NEW` | 退回待审，`seen=false` |

- `favorite=true` 会同时把该项 `seen=true`（收藏即代表看过）。
- **没有任何永久删除动作**：Bridge 不暴露 cleanup / delete 端点，
  审核只改业务状态，绝不删文件。

成功 200（fixture `decision_keep.json` / `decision_reject.json`）：

```json
{
  "success": true,
  "data": {
    "session": { /* SessionSummary */ },
    "item_index": 0,
    "image": { /* 更新后的 MobileImageSummary */ }
  },
  "error": null,
  "request_id": "…"
}
```

- 客户端应以响应里的 `session.seen_count` / `image` 为准，**不要本地 +1**。

### 8.1 409 REVIEW_CONFLICT（乐观锁冲突）

当 `expected_status` 或 `expected_updated_at` 与服务端权威不一致 → **409**
（fixture `review_conflict.json`）：

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "REVIEW_CONFLICT",
    "message": "图片状态已被他处修改",
    "details": {
      "image": { /* 服务端权威 MobileImageSummary */ },
      "current_status": "KEEP",
      "current_updated_at": "2026-10-12T10:02:00.000Z"
    }
  },
  "request_id": "…"
}
```

客户端处理：丢弃本地该项旧视图，用 `details.image` 刷新该位置，
重新让用户决定（不要盲目重试同一 decision）。

### 8.2 其它业务错误码

| HTTP | code | 触发 |
| --- | --- | --- |
| 404 | `REVIEW_SESSION_NOT_FOUND` | 会话不存在 |
| 404 | `REVIEW_ITEM_NOT_FOUND` | queue 里没有该 item_index / image_id |
| 404 | `IMAGE_NOT_FOUND` | 队列项指向的图已不存在 |
| 422 | `DECISION_ACTION_INVALID` | action 不在 `KEEP/REJECT/RESET` |
| 422 | `VALIDATION_ERROR` | 通用参数校验失败 |
| 400 | `PAIRING_CODE_INVALID` | 配对码错/过期/已用 |
| 500 | `INTERNAL_ERROR` | 未处理异常 |

---

## 9. 端点速查表

| 方法 | 路径 | 鉴权 | 成功 | 主要错误 |
| --- | --- | --- | --- | --- |
| GET | `/mobile/system/health` | 开放 | 200 | — |
| GET | `/mobile/pairing/status` | 开放 | 200 `{pairing_available}` | — |
| POST | `/mobile/pairing/verify` | 开放 | 200 token | 400 `PAIRING_CODE_INVALID` |
| POST | `/mobile/review/sessions` | Bearer | 201 SessionSummary | 401 |
| GET | `/mobile/review/sessions/latest` | Bearer | 200 SessionSummary | 404 `REVIEW_SESSION_NOT_FOUND` |
| GET | `/mobile/review/sessions/{id}/queue` | Bearer | 200 `{items,total,page,page_size}` | 401/404 |
| POST | `/mobile/review/sessions/{id}/decision` | Bearer | 200 `{session,item_index,image}` | 401/404/**409 `REVIEW_CONFLICT`**/422 |
| POST | `/mobile/review/sessions/{id}/position` | Bearer | 200 SessionSummary | 401/404/422 |
| POST | `/mobile/review/sessions/{id}/complete` | Bearer | 200 `{…,completed,remaining_count}` | 401/404 |
| GET | `/mobile/images/{id}/thumbnail` | Bearer | 200 `image/webp` | 401/404 |
| GET | `/mobile/images/{id}/preview` | Bearer | 200 `image/webp` | 401/404 |
| GET | `/mobile/images/{id}/original` | Bearer | 200 `image/*` | 401/404 `IMAGE_FILE_MISSING` |

> Desktop loopback(8000) 上的 `POST /api/v1/mobile-review/pairing/code`、
> `GET/POST /api/v1/mobile-review/runtime*` 仅供 Desktop 自用，**手机侧不调用**。
