# MediaReview Android 对接 NSFW 图片审核桥 — 落地指南

> 目标：在 MediaReview Android 现有 `feature/v2` 体系里，新增一条
> **NSFW Studio 图片审核**数据通路，对端为冻结的 Mobile Review Bridge(8767)。
>
> 合同事实源：`MEDIAREVIEW_NSFW_CONTRACT_V1.md`、
> `openapi-mobile-review.json`、`fixtures/*.json`。
> 概念对照：`MEDIAREVIEW_STATE_MAPPING.md`。
>
> 本文只规定 Android 侧新增什么、复用什么、数据流怎么走；不改 Server/Jellyfin。

---

## 1. 新增组件清单与职责

包建议：`feature/v2/data/nsfw/`（api / model / repo / pairing），
`feature/v2/review/nsfw/`（screen / viewmodel）。

| 新增类 | 职责 |
| --- | --- |
| `V2DataMode.NSFW_STUDIO` | 在现有枚举里加一个值，与 DEMO/SERVER 并列 |
| `NsfwStudioProfileStore` | DataStore（独立 name，如 `nsfw_studio_profile`）：存 `baseUrl`、`installationId`、`deviceId`、token；token 用 Keystore AES-GCM 加密 |
| `NsfwUrlNormalize` | 输入 host/IP → 补 `http://` 与默认端口 `:8767`，拒绝 userinfo/query/fragment/path |
| `NsfwPairingRepository` | health gate（`product=nsfw-studio` 且 `api_contract>=1`）→ pairing/status → 用户输码 → pairing/verify 换 token → 落 ProfileStore |
| `NsfwAuthInterceptor`（或复用现有 AuthInterceptor） | 给 authenticated OkHttp 加 `Authorization: Bearer <token>` |
| `NsfwStudioApi` | Retrofit 接口，声明全部 `/mobile/*` 端点（见 §3） |
| `NsfwImage` | `@Serializable` DTO，对应 MobileImageSummary（见合同 §6） |
| `NsfwReviewSessionSummary` | DTO：`id,status,total_count,seen_count,current_index,created_at,updated_at,filter` |
| `NsfwQueuePage` / `NsfwQueueItem` | DTO：`{items:[{index,seen,image:NsfwImage}],total,page,page_size}` |
| `NsfwReviewSessionRepository` | 打开/恢复会话、分页队列、decision、position、complete；双向分页窗口 + Mutex single-flight |
| `NsfwReviewSessionRepositoryRouter` | 按 `V2DataMode.NSFW_STUDIO` 委托 |
| `NsfwImageReviewScreen` + ViewModel | HorizontalPager 看图 + 底栏 KEEP/REJECT/收藏/RESET + 顶栏进度 |

---

## 2. 关键数据流

### 2.1 首次进入（未配对）

```
用户在设置里选 DataMode = NSFW_STUDIO
  → 手动输入电脑 LAN IP（NsfwUrlNormalize 补 http://ip:8767）
  → GET /mobile/system/health（publicHttp，无 token）
      ├─ 不通 / product 错 / api_contract<1 → NsfwStatus.Incompatible，停下
      └─ 通过 → GET /mobile/pairing/status
            ├─ pairing_available=false → 提示"请在 Desktop 上生成配对码"
            └─ pairing_available=true → 弹出 6 位码输入框
                  → POST /mobile/pairing/verify {installation_id, device_name, code}
                        ├─ 200 → token 落 NsfwStudioProfileStore（加密），状态 Online
                        └─ 400 PAIRING_CODE_INVALID → 码错/过期，重输
```

### 2.2 恢复会话（每次进审核页）

```
NsfwReviewSessionRepository.open():
  1. GET /mobile/review/sessions/latest
       ├─ 200 → 拿 SessionSummary（含 current_index）
       └─ 404 REVIEW_SESSION_NOT_FOUND → POST /mobile/review/sessions {filter} → 201
       （其它错误：401/5xx/IO → 直接 Failed，绝不"失败即新建"）
  2. 定位：page = current_index / PAGE_SIZE + 1，只拉那一页
       GET /mobile/review/sessions/{id}/queue?page=&page_size=50
  3. pager 跳到 current_index 对应的本地位置
```

### 2.3 翻页 / 看图

- 双向分页窗口 `firstLoadedPage / lastLoadedPage`，`Mutex` single-flight。
- 合并：按 `item.index` 去重 + 升序；本地定位用
  `items.indexOfFirst { it.index == targetIndex }`，禁止 `idx - baseIndex` 推算。
- 图片加载（复用 ZoomableImage 策略）：
  - 列表/邻页 → `preview_url`（1536 WebP）；
  - 当前页用户放大 → `original_url`；
  - 缩略图 → `thumbnail_url`（512 WebP）。
  - 全部走 `http://<ip>:8767 + <相对路径>`，Coil 带 ETag 缓存。

### 2.4 提交 decision

```
用户点 KEEP / REJECT / 收藏 / RESET
  → ViewModel 取当前图已知的 expected_status / expected_updated_at
  → POST /mobile/review/sessions/{id}/decision
       { item_index, action, favorite, expected_status, expected_updated_at }
       ├─ 200 → 用响应里的 session.seen_count 与 image 刷新 UI（不本地 +1）
       └─ 409 REVIEW_CONFLICT → 用 error.details.image 替换该位置，提示"已被他处修改"，
            不盲目重试，等用户重新决定
  → 翻页/停留时防抖 POST /mobile/review/sessions/{id}/position {item_index}
```

---

## 3. NsfwStudioApi（Retrofit）接口声明要点

baseUrl = `http://<ip>:8767/`；所有方法返回 `Envelope<T>`（图片二进制除外）。

```kotlin
interface NsfwStudioApi {
    @GET("mobile/system/health")
    suspend fun health(): Envelope<HealthDto>                 // publicHttp

    @GET("mobile/pairing/status")
    suspend fun pairingStatus(): Envelope<PairingStatusDto>   // publicHttp

    @POST("mobile/pairing/verify")
    suspend fun pairingVerify(@Body body: PairingVerifyBody): Envelope<PairingVerifyDto> // publicHttp

    @POST("mobile/review/sessions")
    suspend fun createSession(@Body body: CreateSessionBody = CreateSessionBody()): Envelope<NsfwReviewSessionSummary> // 201

    @GET("mobile/review/sessions/latest")
    suspend fun latestSession(): Envelope<NsfwReviewSessionSummary>

    @GET("mobile/review/sessions/{id}/queue")
    suspend fun queue(
        @Path("id") sessionId: String,
        @Query("page") page: Int = 1,
        @Query("page_size") pageSize: Int = 50,
    ): Envelope<NsfwQueuePage>

    @POST("mobile/review/sessions/{id}/decision")
    suspend fun decision(@Path("id") sessionId: String, @Body body: DecisionBody): Envelope<DecisionResult>

    @POST("mobile/review/sessions/{id}/position")
    suspend fun position(@Path("id") sessionId: String, @Body body: PositionBody): Envelope<NsfwReviewSessionSummary>

    @POST("mobile/review/sessions/{id}/complete")
    suspend fun complete(@Path("id") sessionId: String): Envelope<CompleteResult>

    // 图片二进制：用 OkHttp 直接取字节 / 交给 Coil 拼 URL，不通过 Envelope
}
```

DecisionBody 字段与合同一致：`item_index`、`image_id?`、`action`
（`"KEEP"|"REJECT"|"RESET"`）、`favorite: Boolean?`、`expected_status?`、
`expected_updated_at?`。

---

## 4. 配对与 token 存储（Keystore）

- `installationId`：首次启动生成并持久化为稳定 UUID（明文存 ProfileStore 即可），
  跨重新配对保留 —— 这样同一台手机换码后是**同一设备轮换 token**，不是新设备。
- token：`pairing/verify` 成功后**仅本次**拿到，必须立即用
  Android Keystore-backed AES-GCM 加密后落 `NsfwStudioProfileStore`。
  （复用 `CredentialCipher` / `AndroidKeystoreCredentialCipher` 思路。）
- `deviceId` / `paired_at` 一并存，便于设置页展示。
- 401（`UNAUTHORIZED` 或 `DEVICE_REVOKED`）→ 清空本地 token，状态回 AuthRejected，
  引导重新配对。

---

## 5. 409 处理约定

- 每次 decision 前，ViewModel 缓存当前队列项最近一次从服务端拿到的
  `status` / `updated_at` 作为 `expected_*`。
- 命中 409：
  1. 不重试同一请求；
  2. 用 `error.details.image`（权威 NsfwImage）替换本地该 index 位置；
  3. 顶栏/Snackbar 提示"该图已在他处被处理"；
  4. 让用户基于最新状态重新操作。
- 图片二进制端点不包 envelope；decision/session 错误才走 envelope。

---

## 6. 明确复用 / 明确不复用

**复用（思路或代码）：**
- `Envelope<T>` 泛型、`AuthInterceptor` / `TokenProvider` 模式；
- `UrlNormalize` 思路（仅默认端口改成 8767）；
- health → contract gate → verify 的配对 UX；
- `ReviewSessionModels` 的分页 / 绝对 index / resume 纯逻辑（字段名 `index`）；
- `ZoomableImage` / `ZoomMath` / 顶底栏 / 信息面板 / Snackbar 模式。

**不复用（强耦合视频/Jellyfin/删除）：**
- `V2ReviewScreen`（GSY 视频 VerticalPager）；
- `V2ServerMediaRepository`（Jellyfin playback + sprite + libraries + folders）；
- delete queue / nonce 两步提交（NSFW 无永久删除）；
- sprite 雪碧图、重复扫描、播放进度上报。
