# MediaReview Android × NSFW Bridge 测试矩阵

> 范围：MediaReview Android 侧 NSFW 图片审核通路（`V2DataMode.NSFW_STUDIO`）。
> 对端固定为 **NSFW interop client** 或冻结的
> `docs/integration/fixtures/*.json`（即后端 Phase 0.13 已冻结合同）。
>
> 约定：
> - 单测（Unit）：纯本地，用 mock/fixture JSON，不碰网络。
> - 集成（Integration）：起一个本地 stub/内存对端回放 fixtures，走 Retrofit+OkHttp。
> - 真机（Device）：手机连真实 Desktop 同网段，打 `http://<ip>:8767`。
> - 所有断言的路径 / 字段 / 状态码必须与
>   `openapi-mobile-review.json`、`fixtures/*.json` 逐字一致。

---

## 1. 配对与认证

| # | 用例 | 层级 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| P1 | health gate 通过 | Unit/Integ | 对端返回 `mobile_health.json`（`api_contract=1, product=nsfw-studio`） | 判定 Online，继续 pairing 流程 |
| P2 | health 不兼容（api_contract=0） | Unit | 改 fixture `api_contract=0` | 直接 `Incompatible`，**不**发 pairing/verify |
| P3 | health product 不符 | Unit | `product="other"` | `Incompatible` |
| P4 | pairing/status 开放可达 | Integ | `GET /mobile/pairing/status` | 200 envelope，`data.pairing_available` bool（fixture `pairing_status.json`） |
| P5 | 配对成功换 token | Integ | `POST /mobile/pairing/verify` 正确 6 位码 | 200，`data.token` 仅本次返回；token 加密落 Keystore-backed store |
| P6 | 配对码一次性 | Integ | 同一 code 连续 verify 两次 | 第一次 200；第二次 400 `PAIRING_CODE_INVALID` |
| P7 | 配对码过期 | Integ | 注入已过期 fixture | 400 `PAIRING_CODE_INVALID` |
| P8 | 配对码错误位数/非数字 | Integ | code 传 `12345` 或 `abcdef` | 400/422，不换 token |
| P9 | 未授权 401 | Integ | 无 token / 错误 token 打受保护端点 | 401 envelope，`error.code=UNAUTHORIZED`（fixture `error_unauthorized.json`）；状态回 AuthRejected |
| P10 | 设备被吊销 | Integ | 用 revoked 设备 token | 401 `error.code=DEVICE_REVOKED`；引导重新配对 |
| P11 | 同 installation 重配轮换 token | Integ | 同 `installation_id` 再 verify 一次 | 新 token 生效，旧 token 立即 401 |
| P12 | 手动 IP 归一化 | Unit | 输入 `192.168.1.5` / `http://x:8767/` / 带 path 的非法串 | 合法补成 `http://192.168.1.5:8767/`；拒绝 userinfo/query/fragment/path |

---

## 2. Review Session（冻结 / 恢复 / 绝对 index）

| # | 用例 | 层级 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| S1 | 创建会话 | Integ | `POST /mobile/review/sessions` `{filter:{status:NEW,sort:created_desc}}` | **201**，SessionSummary 字段齐（`review_session.json`）：`id,status,total_count,seen_count,current_index,created_at,updated_at,filter` |
| S2 | 默认 filter 缺省 | Unit/Integ | body 传 `{}` | 服务端按 `{status:NEW,sort:created_desc}` 冻结 |
| S3 | 恢复最近会话 | Integ | 已有 active 会话时 `GET /latest` | 200 返回该会话，**不新建** |
| S4 | 无会话时 latest → 新建 | Integ | 先 `GET /latest` 得 404 `REVIEW_SESSION_NOT_FOUND`，再 `POST /sessions` | 仅在明确 404 时新建一次 |
| S5 | 恢复时网络错误不新建 | Integ | `GET /latest` 返回 500/IO | 打开失败 Failed，**绝不**自动新建会话 |
| S6 | 队列冻结不压缩 | Integ | 创建后对某图做 RESET（回 NEW），再翻队列 | 队列成员与 `index` 顺序不变；被 RESET 的图仍在原 index 位置（`seen=false`） |
| S7 | 分页 | Integ | `page=1&page_size=50` 拉队列 | 200 `{items:[{index,seen,image}],total,page,page_size}`（`review_queue_page.json`）；`index` 为 0 基绝对 index |
| S8 | page_size 上限 | Integ | 传 `page_size=201` | 422 校验失败（合同 le=200） |
| S9 | 本地定位按 index 而非偏移 | Unit | 构造含缺洞 index 序列（0,1,3），查 index=3 | `indexOfFirst{it.index==3}` 命中；断言不能用 `3-base` 推算 |
| S10 | 断点恢复只拉目标页 | Unit | `current_index=120, page_size=50` | 计算 `page=3`，只请求第 3 页 |
| S11 | position 记录位置 | Integ | `POST /position {item_index:2}` | 200 SessionSummary，`current_index=2`，`seen` 不变 |
| S12 | position 越界 | Integ | `item_index=total_count` | 422 `POSITION_OUT_OF_RANGE` |
| S13 | complete 未审完不强完成 | Integ | 仍有 `seen=false` 时 `POST /complete` | 200 `{completed:false, remaining_count:n}` |
| S14 | complete 全审完 | Integ | 全部 seen=true 后 complete | 200 `{completed:true, remaining_count:0}`，会话 `status=COMPLETED` |

---

## 3. Decision（KEEP / REJECT / favorite / RESET）

| # | 用例 | 层级 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| D1 | KEEP | Integ | `decision {item_index:0, action:KEEP, expected_status:NEW, expected_updated_at:...}` | 200（`decision_keep.json`）：`image.status=KEEP`，`seen_count+1`，返回更新后 session+image；客户端不本地 +1 |
| D2 | REJECT | Integ | `action=REJECT` | 200（`decision_reject.json`）：`image.status=REJECT` |
| D3 | RESET 回 NEW | Integ | 对 KEEP 过的图 `action=RESET` | `image.status=NEW`，该队列项 `seen=false` |
| D4 | 收藏独立 | Integ | `favorite=true`（action 不传） | `is_favorite=true`，该项 `seen=true`；审核状态不变 |
| D5 | 取消收藏 | Integ | `favorite=false` | `is_favorite=false` |
| D6 | expected_status 不一致 → 409 | Integ | 他处先把图改成 KEEP，本机仍按 NEW 提交 decision | **409** `error.code=REVIEW_CONFLICT`（`review_conflict.json`）；`details.image` 为权威图，`details.current_status/current_updated_at` 齐备 |
| D7 | expected_updated_at 不一致 → 409 | Integ | 仅 updated_at 陈旧 | 409 REVIEW_CONFLICT |
| D8 | 409 客户端处理 | Unit | 收到 409 | 用 `details.image` 替换本地该项，不自动重试，提示用户重新决定 |
| D9 | 非法 action | Integ | `action=DELETE` | 422 `DECISION_ACTION_INVALID` |
| D10 | 无永久删除 | Integ/审计 | 遍历 openapi 路径 | 不存在 delete/cleanup 端点；capabilities 不含 `permanent_delete`；decision 只能改状态 |

---

## 4. 图片内容端点与缓存头

| # | 用例 | 层级 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| C1 | thumbnail | Integ | `GET /mobile/images/{id}/thumbnail`（Bearer） | 200 `image/webp`（约 512）；响应含 `ETag`、`Cache-Control: private, max-age=300`、`X-Content-Type-Options: nosniff` |
| C2 | preview | Integ | `GET .../preview` | 200 `image/webp`（约 1536），同缓存头 |
| C3 | original | Integ | `GET .../original` | 200 `image/*`（按原文件 MIME），同缓存头 |
| C4 | 二进制不包 envelope | Integ | 检查图片端点响应 body | 是原始字节，不是 `{success,data,...}` |
| C5 | ETag 形态 | Unit | 解析 ETag | 形如 `"thumb-<id>-<w>x<h>-<updated_at>"`（preview/original 前缀对应） |
| C6 | If-None-Match 304 | Integ | 二次请求带上次 ETag | 服务端返回 304（Coil 本地缓存命中） |
| C7 | 原图文件缺失 | Integ | 指向缺失文件 | 404 `error.code=IMAGE_FILE_MISSING`（此时是 JSON envelope） |
| C8 | 原图按需加载 | Unit | ZoomableImage 策略 | 仅当前页拉 original；邻页只用 preview/thumbnail |

---

## 5. 网络边界 / 部署守卫

| # | 用例 | 层级 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| N1 | 仅 LAN 审核 API | Integ/审计 | 枚举 8767 路由 | 只有 `system/pairing/images/review`；不存在 jobs/engine/prompts/recipes/assets/cleanup/modules/desktop SPA |
| N2 | 不直连 8000 | Device | 手机侧发起任何请求 | 目标 host 必须是 `:8767`；配对码由 Desktop loopback `:8000 /api/v1/mobile-review/pairing/code` 生成，手机不调用 |
| N3 | 开放端点清单 | Integ | 不带 token 逐个试 | 仅 health / pairing/status / pairing/verify 通；其余一律 401 |
| N4 | request_id 透传 | Unit | 解析 envelope | 每个响应有 `request_id`；响应头 `X-Request-ID` 一致 |
| N5 | 切换服务器重建 client | Unit | baseUrl 改变 | Retrofit baseUrl 不可变，切换后重建 NsfwStudioApi |

---

## 6. 对端说明

- **NSFW interop client**：在 Android 集成测试里用回放式 stub，按上表用例返回
  `fixtures/` 下对应 JSON（health / pairing_status / pairing_verify /
  review_session / review_queue_page / decision_keep / decision_reject /
  review_conflict / error_unauthorized），以保证 Android 侧 DTO 与错误映射
  和冻结合同逐字对齐。
- **真机联调**：Desktop 与手机同 Wi-Fi，Desktop 生成 6 位配对码，
  手机输入 `http://<desktop-lan-ip>:8767` + 配对码，走 P5→S1/S3→D1→C1~C3 全链路。
