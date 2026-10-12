# MediaReview 兼容性审计（服务于 NSFW Studio 手机审核桥对接）

> 审计对象：MediaReview Android / Server，锁定 pinned commit
> `ba19d01aba692f0ed010c625f801738ba306bae4`
> （subject：`test/release: regression gates and alpha9`，作者 esp32-dev，2026-10-09）。
>
> 审计方式：只读。在 `D:\AIHome_2.0_L1_L2\temp\mediareview-ba19d01-audit` 用
> `git worktree add --detach` 拉出独立 detached HEAD，不碰主工作树
> （`D:\AIHome_2.0_L1_L2\projects\mediareview`，HEAD=`4ce9a87`），
> 不向 MediaReview 仓库提交任何内容。
>
> 文档所有路径均为 ba19d01 内相对仓库根的路径。

---

## 1. 事实口径

### 1.1 Repo / Commit

- 远端：`https://github.com/zxingyu178-dot/MediaReview.git`
- 审计锁定 commit：`ba19d01aba692f0ed010c625f801738ba306bae4`
- 主工作树 HEAD（审计期间保持不动）：`4ce9a87 docs(release): record verified Stage8H artifacts and gates`

### 1.2 Android 版本

- `android/app/build.gradle.kts:32-33`
  - `versionCode = 16`
  - `versionName = "2.0.0-alpha9"`
- `applicationId = "com.mediareview.app"`，`namespace = "com.mediareview.app"`
  （`android/app/build.gradle.kts:23,27`）
- `minSdk = 26`，`targetSdk = 35`，`compileSdk = 36`
  （`android/app/build.gradle.kts:28-29,24`）
- 技术栈：Kotlin + Jetpack Compose + Hilt + Retrofit + OkHttp + kotlinx.serialization
  + Coil + Paging 3 + GSYVideoPlayer(Exo2 内核) + AndroidX Media3
  （`android/app/build.gradle.kts:92-157`）。

### 1.3 Server 版本 / API Contract / 端口

- `server/app/__init__.py:3` — `__version__ = "1.2.2"`
- `server/app/__init__.py:10` — `SERVER_API_CONTRACT = 2`
- `server/app/__init__.py:14-21` — `SERVER_CAPABILITIES`：
  `review_session`、`review_nearest`、`organize`、`delete_nonce`、
  `duplicates_paged`、`library_selection`
- `server/app/core/config.py:165-168` — `ServerConfig.host = "0.0.0.0"`，
  `port: int = Field(default=8766, ge=1, le=65535)`，**默认端口 8766**。
- 启动入口：`server/run_server.py` + `server/app/main.py`（FastAPI，
  `docs_url="/api/docs"`，`openapi_url="/api/openapi.json"`）。
- 路由聚合：`server/app/api/v1/__init__.py:22` — 统一前缀 `/api/v1`。
- 持久化：SQLite（SQLAlchemy + Alembic），`server/app/db/`，
  数据根默认 `%ProgramData%\MediaReview`（`server/app/core/config.py:24`）。

### 1.4 Envelope 结构

服务端（`server/app/core/responses.py:18-28`）：

```python
class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None

class Envelope[T](BaseModel):
    success: bool = True
    data: T | None = None
    error: ErrorBody | None = None
    request_id: str = ""
```

成功：`{"success": true, "data": ..., "error": null, "request_id": "..."}`
失败：`{"success": false, "data": null, "error": {code, message, details}, "request_id": "..."}`

Android 端镜像（`android/app/src/main/java/com/mediareview/app/core/model/ApiModels.kt:11-15`）：

```kotlin
@Serializable
data class Envelope<T>(
    val success: Boolean,
    val data: T? = null,
    val error: ErrorBody? = null,
    val request_id: String = "",
)
```

所有受保护业务接口都包在 `Envelope[...]` 里；HTTP 状态码与 Envelope.error.code
同时存在（见 `server/app/main.py:44-56` 的 `_HTTP_STATUS_MAP`：
`UNAUTHORIZED / FORBIDDEN / NOT_FOUND / VALIDATION_ERROR / CONFLICT ...`）。

### 1.5 Pairing 流程

服务端：
- `server/app/services/pairing.py` — 一次性 6 位配对码 + bearer token 闭环：
  - `_CODE_LENGTH = 6`，`_DEFAULT_TTL_MINUTES = 10`（`pairing.py:26-28`）
  - token 前缀 `mr_` + 40 位随机（`pairing.py:42-45`）
  - 服务端只存 `SHA-256(token)`，不明文（`pairing.py:48-49`）
  - 重新配对会轮换 token，旧 token 立即失效（`pairing.py:99-102`）
- `server/app/api/v1/pairing.py:27` — 路由前缀 `/pairing`，挂在 `/api/v1` 下：
  - `GET  /pairing/status`（开放，返回 `pairing_required / device_count`）
  - `POST /pairing/code`（**仅 loopback 或管理后台**；远程默认 403，见
    `pairing.py:97-111` 与 `server/app/core/config.py:262-267` 的
    `pairing_code_remote_allowed=False`）
  - `POST /pairing/verify` `{device_id, code}` → `{paired, token}`
  - `GET  /pairing/devices`（受保护）
  - `POST /pairing/revoke`（受保护，同时尽力在 Jellyfin 侧撤销设备播放 key）
  - `POST /pairing/codes/clean`（受保护）
- 统一认证依赖 `server/app/api/v1/auth.py`：
  - `require_auth` 读 `Authorization: Bearer <token>`，按 SHA-256 哈希查
    `PairedDevice` 且 `revoked=False`；`pairing_required=False` 时放行。
  - `require_localhost_or_auth`：loopback 直连放行，否则走 `require_auth`
    （用于 `/system/info`、`/system/storage`、管理后台等敏感接口）。

Android 端：
- `android/.../core/pairing/UrlNormalize.kt:4` — `DEFAULT_PORT = 8766`；
  `normalizeBaseUrl(input)` 自动补 `http://` 与 `:8766`，拒绝 userinfo/query/fragment/path。
- `android/.../core/pairing/PairingRepository.kt:30` —
  `const val REQUIRED_SERVER_API_CONTRACT: Int = 2`；
  `checkHealthy(baseUrl)` 先打 `/system/health`，若 `api_contract < 2` 直接返回
  `Result.Incompatible`，**不再继续** pairing / jellyfin / media 探测
  （`PairingRepository.kt:140-162`）。
- `android/.../core/datastore/ServerProfileStore.kt`：
  - DataStore name = `media_review_server`
  - token 以 Android Keystore-backed AES-GCM 加密落盘
    （`CredentialCipher.kt` / `AndroidKeystoreCredentialCipher`）
  - `deviceId` 为首次生成后稳定 UUID，跨重新配对保留
- `android/.../core/network/AuthInterceptor.kt` — OkHttp Interceptor，
  每次请求从 `TokenProvider` 取当前 origin 的 token，附加
  `Authorization: Bearer <token>`；无 token 则不附加。
- `android/.../core/network/ApiFactory.kt` — Retrofit baseUrl 不可变，
  切换服务器时重建 `MediaReviewApi`；区分 `authenticatedHttp` / `publicHttp`
  两个 OkHttp 实例。

### 1.6 Review Session 语义

服务端 `server/app/api/v1/review.py`（路由前缀 `/review`，挂在 `/api/v1`）：

| 方法 + 路径 | 语义 |
| --- | --- |
| `POST /review/sessions` | 创建会话；body 只提交 `source:{filter, sort}`，队列由服务端按已选媒体库构建并固化为一次性队列（`review.py:98-116`） |
| `GET  /review/sessions/latest` | 断点恢复：取最近 active 会话；无 active 时 404（`review.py:119-126`） |
| `GET  /review/sessions/{id}` | 会话总览（source 快照 + 服务端权威 progress） |
| `GET  /review/sessions/{id}/queue?page&page_size` | 分页队列；`page_size` 默认 50，上限 200；每项含 **绝对 index + seen**（`review.py:148-182`） |
| `GET  /review/sessions/{id}/nearest?index&direction=forward\|backward\|nearest` | SQL 直查稀疏队列最近可用项；返回 `{"index": int|null}`，**null = 服务端明确无可用**，与"网络失败"严格区分（`review.py:252-273`） |
| `POST /review/sessions/{id}/seen` | `{media_id, seen}`；返回**服务端权威** `total/seen/unavailable/remaining/completed`，幂等；客户端**不得自行 +1**（`review.py:185-201`） |
| `POST /review/sessions/{id}/position` | `{index}` 更新 `current_index`，作为下次断点恢复依据（`review.py:208-220`） |
| `POST /review/sessions/{id}/advance` | 前进一项，当前项视为已看 |
| `POST /review/sessions/{id}/complete` | fail-closed：`remaining_count > 0` 时拒绝（`review.py:234-249`） |

校验规则（`review.py:74-95`）：
- `filter.media_type ∈ {video, image}`
- `sort_by ∈ {name, created, size, duration, resolution, random}`
- `sort_order ∈ {asc, desc}`
- `random` 排序时服务端自动补 `random_seed`。

Android 端：
- 接口 `android/.../feature/v2/review/data/V2ReviewSessionRepository.kt`
- 生产实现 `V2ServerReviewSessionRepository.kt:26-56`（头注释完整复述了上述合同）：
  - 恢复路径 = `latest` → 仅在明确 404 时新建；其他错误一律
    `ReviewSessionOpen.Failed`，**绝不"失败即新建"**
    （`V2ServerReviewSessionRepository.kt:111-120`）
  - 恢复定位 = `current_index` → 1 次 `/nearest` SQL 命中 → 只拉目标页
  - 双向分页窗口 `firstLoadedPage / lastLoadedPage`，`Mutex` single-flight
- 纯逻辑 `ReviewSessionModels.kt`：
  - `ReviewQueueItemUi.absoluteIndex`：服务端**永不压缩绝对索引**（缺项留洞）
    （`ReviewSessionModels.kt:12-13, 95-97`）
  - `ReviewQueuePaging.PAGE_SIZE = 50`（`:177`）
  - `mergeItems` 按 `absoluteIndex` 去重 + 升序（`:207-213`）
  - `localIndexOf` 必须 `indexOfFirst { absoluteIndex == ... }`，
    禁止用 `absoluteIndex - baseIndex` 推算（`:121-122`，注释明确 600/601 缺 602 的反例）
  - `resumePlan(absoluteIndex)` → `page = idx/pageSize + 1`
- 路由 `V2ReviewSessionRepositoryRouter.kt`：UI 只依赖 `V2ReviewSessionRepository`，
  按 `V2DataMode` 委托 `DemoReviewSessionRepository` / `V2ServerReviewSessionRepository`。

### 1.7 Media Repository

服务端 `server/app/api/v1/media.py`：
- `GET /api/v1/media` — 只查 SQLite 索引（`MediaCacheIndex`），不等待 Jellyfin；
  分页 `page / page_size`，带 `sort_by / sort_order / search / folder_id / exclude_favorites / media_type`
- `GET /api/v1/media/folders` — 按父目录聚合，文件夹封面走同一缩略图代理
- `GET /api/v1/media/{media_id}/thumbnail?v=<source_version>` — 需配对的代理缩略图；
  `source_version` 由内容指纹派生，做客户端缓存失效（`media.py:109-116`）
- `GET /api/v1/media/{media_id}/original` — 仅 `media_type=image` 返回代理原图 URL
  （`media.py:119-122`）；视频走 Jellyfin 直连，**不经中间层代理**
- `POST /api/v1/media/refresh` — 幂等编排持久化媒体刷新任务
  （`server/app/services/media_index.py`，与 Jellyfin 同步强耦合）
- `MediaSummary` 字段（`media.py:47-69`）：
  `media_id, name, media_type, library_id, duration_ms, size_bytes, width, height,
  container, created_at, modified_at, cover_url, original_url, folder_id, folder_name, is_favorite`

Android 端：
- 接口 `android/.../feature/v2/data/MediaRepository.kt`
- 生产实现 `feature/v2/data/server/V2ServerMediaRepository.kt`：
  - 架构注释明确：`V2 UI → V2MediaRepositoryRouter → V2ServerMediaRepository
    → MediaReviewApi → FastAPI → Jellyfin`（`:53-55`）
  - 复用 `ApiFactory / MediaReviewApi / ServerProfileStore / TokenProvider / MediaUrlResolver`
  - 强耦合点：`V2PlaybackResolver`（Jellyfin 设备级 stream key）、
    sprite manifest 缓存、library selection、folders、album cover。

### 1.8 Image Viewer

- `feature/v2/viewer/V2ImageViewer.kt`：
  - `HorizontalPager` 左右翻图，scale==1 翻页、scale>1 拖动图片
  - 单击显隐 UI；双击 1.0x↔2.5x；双指 1–5x 缩放；平移带边界
  - 预加载 N-1 / N+1 / N+2
  - `ImageViewerContext.build(allIds, isImage, initialMediaId, ...)`
    只保留 IMAGE 类型，按 `initialMediaId` 重算起始索引
- `feature/v2/viewer/ZoomableImage.kt`：
  - Coil `rememberAsyncImagePainter`
  - `shouldLoadFullResolution(page, currentPage)`：**只有当前页**请求原图，
    邻页只显示已缓存封面，避免 5 张原图同时下载
- 配套：`ZoomMath.kt`、`ImageViewerTopBar.kt`、`ImageViewerBottomBar.kt`、
  `ImageInfoSheet.kt`、`state/AlbumPagingController.kt`、
  `state/ViewerPendingDeleteController.kt`。

### 1.9 DataMode · Router 现状

- `feature/v2/data/V2DataMode.kt:24` — `enum class V2DataMode { DEMO, SERVER }`
- DataStore name = `mediareview_v2_data_source`，key = `data_mode`，默认 `DEMO`
  （`V2DataMode.kt:16,40,74-75`）
- `V2DataModeStore` 启动只读本持久化值，**不阻塞首页、不做网络请求**
- `V2MediaRepositoryRouter.kt:39-53`：
  - UI 永远只依赖 `MediaRepository`，Router 按 `modeStore.mode.value` 委托
  - `dataActive()` 在 `V2ServerStatus.Incompatible` 时直接抛
    `ServerIncompatibleException`，避免首页一串 404
- `feature/v2/data/server/V2ServerStatus.kt`：
  - 状态机 `Unconfigured / Probing / Online / Offline / AuthRejected / Incompatible`
  - **Online 只能由 health probe 建立**；普通业务请求成功不会把状态提升为 Online
  - 401 → `AuthRejected`；IOException → `Offline`
  - 兼容 Gate 唯一判据：`data.api_contract >= REQUIRED_SERVER_API_CONTRACT (= 2)`
- `V2ReviewSessionRepositoryRouter.kt` 与 Media Router 同构，按 DataMode 委托 Demo/Server。

---

## 2. 可复用（建议 NSFW Studio 手机端直接借鉴 / 复制思路）

| 能力 | MediaReview 证据路径 | 复用建议 |
| --- | --- | --- |
| **Envelope 响应包** | `server/app/core/responses.py`；`android/.../core/model/ApiModels.kt:11-15` | NSFW Studio 后端（`/api/v1/mobile/*`）保持同形：`success / data / error{code,message,details} / request_id`；Android 端可直接复用 `Envelope<T>` 泛型类 |
| **Bearer AuthInterceptor 思路** | `android/.../core/network/AuthInterceptor.kt`；`android/.../core/network/TokenProvider.kt`；`server/app/api/v1/auth.py` | 每次请求从 provider 取当前 origin 的 token，附加 `Authorization: Bearer <token>`；服务端只存 SHA-256 哈希；401 → AuthRejected 状态机 |
| **手动 IP + 配对码 UX** | `android/.../core/pairing/UrlNormalize.kt`；`PairingRepository.kt`（health → contract gate → verify）；`server/app/api/v1/pairing.py` | 输入框只问 host/IP；自动补 scheme 与默认端口；先打 health 做 contract gate，再问 6 位配对码；配对码由服务端本机/管理后台展示，手机端不调 `/pairing/code` |
| **分页** | `server/app/api/v1/review.py:148-182`；`android/.../feature/v2/review/data/ReviewSessionModels.kt`（PAGE_SIZE=50、`mergeItems` 按绝对索引去重、`isAtEnd` 按页边界）；`/media?page&page_size` | 双向分页窗口、single-flight Mutex、按绝对索引合并去重、页边界判尾、`prependedCount` 补偿 pager 偏移 |
| **ZoomableImage** | `android/.../feature/v2/viewer/ZoomableImage.kt`；`ZoomMath.kt`；`V2ImageViewer.kt` | 双击 1.0↔2.5x、双指 1–5x、平移边界、**只对当前页加载原图**（邻页用封面）、Coil 集成；可整体拷贝到 NSFW 模块 |
| **absolute-index · resume** | `server/app/api/v1/review.py:208-220,252-273`；`ReviewSessionModels.kt:12-13,121-122,180-186` | 服务端保留绝对索引（缺项留洞不压缩）；客户端 `indexOfFirst { absoluteIndex == ... }` 映射本地 pager 位置；`/nearest?index&direction` 一次 SQL 命中恢复点；`/position` 回写 `current_index` |

附加可复用：
- 健康检查 + contract gate 模式（`V2ServerHealthMonitor`，
  `V2ServerStatus.kt:111-162`）：health → contract → 1 条业务请求验证 token，
  三步轻量探测，不串联旧四段检查。
- `ServerProfileStore` 的凭据存储思路：baseUrl 明文 + token Keystore AES-GCM 加密 +
  稳定 `installationId`（UUID）。
- Review Session 的 fail-closed 完成语义（`remaining > 0` 拒绝 complete）。

---

## 3. 不应复用（MediaReview 强耦合 Jellyfin / 视频场景，NSFW Studio 不要拖进来）

| 不要复用 | 证据路径 | 原因 |
| --- | --- | --- |
| **Jellyfin Library 接入** | `server/app/adapters/jellyfin/{client,manager,mapper,models}.py`；`server/app/api/v1/jellyfin.py`；`server/app/api/v1/libraries.py`；`server/app/services/media_index.py` | MediaReview 的"媒体库"= Jellyfin Library Selection + 全量同步到 SQLite；NSFW Studio 有自己的图库源，**不得冒充 Jellyfin** |
| **视频播放栈** | `android/.../feature/v2/player/gsy/`、`feature/v2/player/native/`、`V2NativePlayerViewModel.kt`；`android/app/build.gradle.kts:131-137`（GSY Exo2 + Media3）；`server/app/api/v1/media.py` 的 `/media/{id}/playback`、`/media/{id}/progress` | NSFW Studio 是**图片审核**，不需要播放器、不需要播放进度上报、不需要 Exo2 |
| **Sprite 雪碧图** | `server/app/services/sprite.py`；`server/app/api/v1/cache.py`；`android/.../feature/v2/home/SpritePreview.kt`；`V2ServerMediaRepository.prepareSprite/spriteUri/spriteManifest` | Sprite 是视频预览条，图片场景无用 |
| **重复扫描** | `server/app/services/duplicate_scanner.py`、`hash_tasks.py`、`hashing.py`、`hash_contract.py`；`server/app/api/v1/duplicates.py`；`feature/v2/organize/duplicates/` | 基于 FFmpeg/感知哈希的视频重复检测，NSFW 审核流不需要 |
| **MediaReview delete queue 原语义** | `server/app/services/delete_queue.py`；`server/app/api/v1/delete_queue.py`；`feature/v2/organize/delete/` | 两步 nonce commit 绑定到 `media_cache_index` 里的**真实文件路径**，删除后清理 Jellyfin 索引；NSFW Studio 的审核动作（接受/拒绝/待定）是业务状态流转，不是文件删除，不要套用这套 nonce/TOCTOU 文件删除合同 |
| **Server DB schema** | `server/app/db/models.py`；表：`media_cache_index / favorite / delete_queue / review_session / review_session_item / sprite_manifest / background_task / paired_device / media_sync_state / duplicate_*` | 这些表都是围绕 Jellyfin 索引 + 视频审阅构建；NSFW Studio 应有自己的库表（图片元数据、审核标签、会话、标注） |

---

## 4. 边界（关键：NSFW Studio 不能冒充 Jellyfin）

MediaReview 当前 `SERVER` 模式 = **MediaReview Server + Jellyfin**：
- `server/app/main.py:71-72` 启动 `JellyfinClientManager`；
- `server/app/core/config.py:171-252` 的 `JellyfinConfig` 整段围绕 Jellyfin
  `url / api_key / user_id / client_url`；
- `V2ServerMediaRepository.kt:53-55` 注释明确数据通路末端是 Jellyfin；
- Pairing revoke 还会同步在 Jellyfin 侧撤销设备播放 key
  （`server/app/api/v1/pairing.py:121-138`）。

NSFW Studio 手机审核桥**必须独立成路**，不得复用/冒充上述链路：

1. **新增独立 `V2DataMode.NSFW_STUDIO`**（与 `DEMO / SERVER` 并列），
   不要在 `V2DataMode` 上做"切换 SERVER 时改 endpoint"的偷偷替换。
2. **独立 `NsfwStudioProfileStore`**：新建自己的 DataStore name（例如
   `nsfw_studio_profile`），**不要**覆盖现有 `media_review_server`
   （`ServerProfileStore.kt:13`）与 `mediareview_v2_data_source`
   （`V2DataMode.kt:16`）的 key；token 加密仍可复用 Keystore AES-GCM 思路。
3. **独立 `NsfwStudioApi`**：Retrofit endpoint 前缀 `/api/v1/mobile/*`，
   不复用 `MediaReviewApi.kt` 里那一组 `/api/v1/{system,pairing,media,review,favorites,delete-queue,duplicates,...}`。
   Envelope 形状可照搬，但接口清单是 NSFW 自己的。
4. **独立 `NsfwImage` / `NsfwReviewSessionRepository`**：
   - 不要塞进 `V2ServerMediaRepository.kt`（那里面是 Jellyfin playback + sprite +
     libraries + folders 的耦合体）。
   - 按现有 Router 范式新增 `NsfwImageRepositoryRouter` / `NsfwReviewSessionRepositoryRouter`
     （或直接在 NSFW 模块内自管，不进 V2 根 Router）。
5. **新建 `NsfwImageReviewScreen`**：
   - **不要**复用 `feature/v2/review/V2ReviewScreen.kt`——它是视频专用
     （`V2ReviewScreen.kt:75-79` 直接 `import com.shuyu.gsyvideoplayer.*`，
     整页 VerticalPager + GSYPlayerSurface + 手势/进度条）。
   - 可复用：`ZoomableImage.kt`、`ZoomMath.kt`、`V2ImageViewer.kt` 的顶/底栏与
     信息面板思路（`ImageViewerTopBar.kt / ImageViewerBottomBar.kt / ImageInfoSheet.kt`）、
     按钮与 Snackbar 模式、`ReviewSessionModels.kt` 的分页/绝对索引/resume 纯逻辑。
6. **服务端边界**：NSFW Studio 后端不暴露 Jellyfin、不读 `media_cache_index`、
   不接 `paired_device / review_session / delete_queue` 这套表；它自己实现
   Envelope + Bearer + 自己的 pairing（或直接信任内网）+ 自己的 review session 语义。

---

## 5. 审计过程只读性声明

- 主工作树 `D:\AIHome_2.0_L1_L2\projects\mediareview` HEAD 始终为 `4ce9a87`，
  未做任何 checkout / 切换分支 / 修改 / 提交。
- 调查在独立 detached worktree `D:\AIHome_2.0_L1_L2\temp\mediareview-ba19d01-audit`
  （`ba19d01`）中完成，调查结束后应 `git worktree remove` 清理。
- 本文档本身提交到 **phase013 worktree**
  `D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-phase013`（分支
  `feature/phase0.13-mobile-review-workspace`），仅 `git add` 本 md 文件，
  不 push，不向 MediaReview 仓库写任何东西。
