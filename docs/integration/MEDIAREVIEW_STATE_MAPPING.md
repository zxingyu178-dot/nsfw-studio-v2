# MediaReview 概念 ↔ NSFW Studio 概念映射表

> 用途：在 MediaReview Android 代码库里新增 NSFW 图片审核能力时，
> 明确"哪些现有概念可以照搬思路 / 哪些必须新建独立组件 / 哪些绝不能碰"。
>
> 事实源：
> - 审计文档：`docs/integration/MEDIAREVIEW_COMPATIBILITY_AUDIT.md`
>   （MediaReview pinned commit `ba19d01aba692f0ed010c625f801738ba306bae4`）。
> - NSFW 冻结合同：`docs/integration/openapi-mobile-review.json`、
>   `docs/integration/fixtures/*.json`、`MEDIAREVIEW_NSFW_CONTRACT_V1.md`。
>
> 核心原则：**新增独立 `V2DataMode.NSFW_STUDIO` 与一整套并行组件，
> 不覆盖 Server / Jellyfin 链路，不向 MediaReview 仓库提交任何内容。**

---

## 1. 总览：一套新平行栈，而不是改 Server 栈

MediaReview 现状：

```
V2 UI → V2MediaRepositoryRouter → (DEMO | SERVER)
                                   └─ SERVER: V2ServerMediaRepository → MediaReviewApi → FastAPI(8766) → Jellyfin
```

NSFW 目标（新增并列分支，不动 SERVER 分支）：

```
V2 UI → V2MediaRepositoryRouter → DEMO | SERVER | NSFW_STUDIO
                                                  └─ NSFW_STUDIO: NsfwImageRepositoryRouter
                                                       → NsfwImageReviewScreen（独立）
                                                       → NsfwStudioApi → NSFW Bridge(8767) → NSFW Studio 图库
```

- `DEMO` / `SERVER` 两个现有分支**一行不改**。
- NSFW 分支复用的是**模式**（Envelope / Bearer 拦截器 / 分页 / 绝对 index /
  可缩放看图），不是复用那几类与 Jellyfin / 视频强耦合的具体类。

---

## 2. 概念映射表

| MediaReview 现有概念（ba19d01 证据路径） | NSFW 对应概念 | 处置 | 说明 |
| --- | --- | --- | --- |
| **V2DataMode** `enum { DEMO, SERVER }`（`feature/v2/data/V2DataMode.kt:24`） | **新增 `V2DataMode.NSFW_STUDIO`** | 新增枚举值 | 与 DEMO/SERVER 并列；DataStore key 仍用 `mediareview_v2_data_source` 的 `data_mode`，只是多一个可选值。**禁止**用"切换 SERVER 时改 endpoint"的偷换方式。 |
| **V2DataModeStore**（DataStore name `mediareview_v2_data_source`） | 复用同一个 DataStore 读 `data_mode` | 复用 | 不新建第二个 data-mode DataStore；启动只读持久化值、不阻塞首页、不发网络请求。 |
| **ServerProfileStore**（DataStore name `media_review_server`；token Keystore AES-GCM 加密；稳定 UUID deviceId） | **新建 `NsfwStudioProfileStore`** | 独立新建，思路复用 | DataStore name 用独立的（如 `nsfw_studio_profile`），**不要覆盖** `media_review_server`。token 加密仍走 Android Keystore-backed AES-GCM；`installationId` 首次生成后稳定 UUID，跨重新配对保留。baseUrl 明文、token 加密落盘。 |
| **MediaReviewApi**（Retrofit 接口，`/api/v1/{system,pairing,media,review,favorites,delete-queue,duplicates,...}`） | **新建 `NsfwStudioApi`** | 独立新建，形状照搬 | endpoint 全部是 NSFW Bridge 的 `/mobile/*`（见合同速查表）。Envelope 泛型 `Envelope<T>` 可直接复用 `core/model/ApiModels.kt`。 |
| **ApiFactory**（`authenticatedHttp` / `publicHttp` 两个 OkHttp 实例；baseUrl 不可变，切服务器重建） | **新建 Nsfw 侧 factory**（或复用双实例思路） | 思路复用 | 一个 public OkHttp（health / pairing），一个 authenticated OkHttp（挂 `AuthInterceptor`）。baseUrl = `http://<ip>:8767`，切换服务器时重建 `NsfwStudioApi`。 |
| **AuthInterceptor**（OkHttp Interceptor，每次请求从 TokenProvider 取当前 origin 的 token，附 `Authorization: Bearer <token>`；无 token 不附） | 直接复用 / 复制到 NSFW 模块 | 复用 | 开放端点（health / pairing）走 publicHttp，不带 token；其余走 authenticatedHttp。 |
| **TokenProvider**（按 origin 取 token） | NSFW 侧 TokenProvider（读 NsfwStudioProfileStore） | 思路复用 | 401 → 状态机 AuthRejected，清 token 回配对页。 |
| **PairingRepository**（health → contract gate → verify；`REQUIRED_SERVER_API_CONTRACT=2`） | **新建 `NsfwPairingRepository`** | 思路复用，阈值不同 | gate 改为 `api_contract >= 1` 且 `product == "nsfw-studio"`。流程：`GET /mobile/system/health` → `GET /mobile/pairing/status` → 用户输入 6 位码 → `POST /mobile/pairing/verify`。手机侧**不调用**生成配对码的端点（那是 Desktop loopback 8000 的事）。 |
| **UrlNormalize**（`DEFAULT_PORT=8766`；自动补 `http://` 与端口；拒绝 userinfo/query/fragment/path） | **新建 NSFW 版 UrlNormalize**（默认端口 8767） | 思路复用 | 输入框只问 host/IP，自动补 `http://` 与 `:8767`，拒绝多余组件。 |
| **Envelope<T>**（`core/model/ApiModels.kt:11-15`，`success/data/error{code,message,details}/request_id`） | 直接复用 | 复用 | NSFW Bridge 与 MediaReview Server envelope 同形。 |
| **MediaSummary**（`media_id,name,media_type,library_id,duration_ms,size_bytes,width,height,container,created_at,modified_at,cover_url,original_url,folder_id,folder_name,is_favorite`） | **新建 `NsfwImage`（MobileImageSummary）** | 独立新建 | 字段以 NSFW 合同为准：`image_id,width,height,created_at,updated_at,status,is_favorite,kind,job_id,seed,thumbnail_url,preview_url,original_url`。**没有** duration/container/folder/library/video 字段。 |
| **V2ServerMediaRepository**（Jellyfin playback + sprite + libraries + folders 耦合体） | **不要塞进去**；新建 `NsfwImageRepository` | 独立新建 | NSFW 仓库只做：拉队列页、decision、position、complete、解析三档图片 URL。 |
| **V2ReviewSessionRepository / V2ServerReviewSessionRepository**（恢复 latest→仅 404 新建；current_index→nearest→只拉目标页；双向分页窗口；Mutex single-flight） | **新建 `NsfwReviewSessionRepository`** | 思路复用 | 合同差异：NSFW 没有 `/nearest` 端点，恢复 = `GET /latest` 拿 `current_index` → 算 `page = current_index/page_size + 1` → 只拉那一页。同样"仅 404 才新建，其它错误绝不新建"。 |
| **ReviewSessionModels**（`absoluteIndex` 永不压缩；`PAGE_SIZE=50`；`mergeItems` 按绝对 index 去重升序；`localIndexOf` 用 `indexOfFirst`；`resumePlan(idx)=idx/pageSize+1`） | 复制纯逻辑到 NSFW 模块 | 复用（纯逻辑） | NSFW 队列项字段叫 `index`（不叫 `absoluteIndex`），映射时对应。`PAGE_SIZE=50`、`page_size` 上限 200 与合同一致。**禁止** `idx - baseIndex` 推算本地位置。 |
| **V2ReviewSessionRepositoryRouter**（按 V2DataMode 委托 Demo/Server） | 同构新增 NSFW 分支 | 思路复用 | UI 只依赖抽象仓库，Router 按 `mode == NSFW_STUDIO` 委托 `NsfwReviewSessionRepository`。 |
| **V2ReviewScreen**（视频专用：`VerticalPager` + GSYPlayerSurface + 进度条/手势） | **不复用** | 禁用 | 它 `import com.shuyu.gsyvideoplayer.*`，是视频页。NSFW 是图片审核。 |
| **V2ImageViewer / ZoomableImage / ZoomMath**（HorizontalPager；双击 1.0↔2.5x；双指 1–5x；只对当前页加载原图；邻页用封面） | **新建 `NsfwImageReviewScreen` 时复用/拷贝这些** | 复用 | 图片缩放、翻页、预加载 N-1/N+1/N+2、当前页才拉 original 的策略直接搬。 |
| **ImageViewerTopBar / BottomBar / ImageInfoSheet** | 复用思路 | 复用 | 顶栏显示 session 进度（`seen_count/total_count`），底栏放 KEEP / REJECT / 收藏 / RESET 按钮。 |
| **ReviewPendingDeleteController / delete queue（nonce 两步提交）** | **不复用** | 禁用 | NSFW decision 是业务状态流转（NEW/KEEP/REJECT），**无永久删除**，不要套 nonce/TOCTOU 文件删除合同。 |
| **V2ServerStatus**（Unconfigured/Probing/Online/Offline/AuthRejected/Incompatible；Online 只能由 health probe 建立） | NSFW 侧对等状态机 | 思路复用 | gate 判据换成 `api_contract >= 1 && product == "nsfw-studio"`；401→AuthRejected；IO→Offline。 |
| **Jellyfin adapters / libraries / media_index / sprite / duplicates / playback** | **完全不碰** | 禁用 | NSFW Bridge 不接 Jellyfin、不读 `media_cache_index`、不做视频预览条、不做感知哈希重复检测。 |

---

## 3. 必须新增（NSFW 专属，平行存在）

1. `V2DataMode.NSFW_STUDIO` 枚举值。
2. `NsfwStudioProfileStore`（独立 DataStore name，token Keystore AES-GCM）。
3. `NsfwStudioApi`（Retrofit，`/mobile/*` 全套）。
4. `NsfwImage` DTO（MobileImageSummary 形状）+ `NsfwReviewSessionSummary` DTO。
5. `NsfwPairingRepository`（health gate contract=1 → status → verify）。
6. `NsfwImageRepository` / `NsfwReviewSessionRepository`（或合为一个 NSFW 仓库）。
7. `NsfwImageRepositoryRouter` / `NsfwReviewSessionRepositoryRouter`（按 DataMode 委托）。
8. `NsfwImageReviewScreen`（HorizontalPager + 复用 ZoomableImage）。
9. NSFW 侧错误映射：`REVIEW_CONFLICT / UNAUTHORIZED / DEVICE_REVOKED /
   REVIEW_SESSION_NOT_FOUND / PAIRING_CODE_INVALID` 等。

---

## 4. 明确不要覆盖 / 不要触碰

- 不要改 `V2ServerMediaRepository`、`MediaReviewApi`、`ServerProfileStore`
  （DataStore name `media_review_server`）、`mediareview_v2_data_source`
  的已有 key 语义。
- 不要把 NSFW endpoint 塞进 `MediaReviewApi.kt`。
- 不要复用 `V2ReviewScreen` / GSY 播放栈 / sprite / duplicates / delete queue。
- 不要让 NSFW 冒充 Jellyfin Library。
- 本批文档只落在 **phase013 worktree**，不向 MediaReview 仓库写任何内容。
