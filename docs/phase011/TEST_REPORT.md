# Phase 0.11 测试报告（TEST_REPORT）

> 所有计数为真实执行结果。真实生图集成测试 `test_comfyui_integration.py` 按项目约定始终 ignore
> （本机 8188 无 ComfyUI、且不依赖真实生成）。

## 一、门禁与最终计数

| 套件 | 基线 | 最终 | 增量 | 结果 |
|---|---|---|---|---|
| Backend pytest | 280 passed | **312 passed** | **+32（只增）** | ✅ |
| Frontend vitest | 121 passed | **130 passed** | **+9（只增）** | ✅ |
| Frontend typecheck (tsc --noEmit) | 通过 | 通过 | — | ✅ |
| Frontend build (vite) | 通过 | 通过 | — | ✅ |

Backend 命令（worktree 根）：`.venv\Scripts\python.exe -m pytest --ignore=tests/backend/test_comfyui_integration.py`
Frontend 命令（frontend/）：`npm run typecheck` / `npm test` / `npm run build`

## 二、Backend 新增测试文件与覆盖

| 文件 | 覆盖点 |
|---|---|
| `test_image_pagination.py` | page/page_size、has_next、sort（created_desc/asc/favorite/size）、status 过滤、历史可完整访问、旧 limit/offset 兼容 |
| `test_thumbnail_service.py` | 512px WebP q80 生成、尺寸/比例、缺失按需生成、损坏原图 THUMBNAIL_FAILED、backfill 单张失败跳过 |
| `test_image_variant.py` | image_variants 记录、variant_type、thumbnail 部分唯一约束、变体不污染 images |
| `test_review_status.py` | NEW/KEEP/FAVORITE/REJECT/ARCHIVED 流转、reviewed_at、FAVORITE↔favorite 同步、双写旧 review_status、batch-status |
| `test_cleanup_rejected.py` | 两阶段预览/真删、删 original+variants+DB、清 Job 输出指针、外键顺序、空目录移除、failed 隔离 |
| `test_image_reference_protection.py` | 被 Prompt/Asset/Recipe/派生/活跃 Job 引用的图跳过计入 protected、cannot 删除被引用图、不留悬空 |

同步更新（非删除）：test_migration_upgrade / test_phase4_backfill（golden 列表 +0015/0016）、
test_health_api（SPA 根路由两种环境）、test_data_dirs（+images/thumbnails）。

## 三、Frontend 新增测试覆盖

| 测试 | 覆盖点 |
|---|---|
| GalleryPagination | 首屏 40、IntersectionObserver 哨兵触发追加 page2、切筛选/排序重置 |
| ThumbnailLoading | 进入 viewport 前占位、进入后 thumbnail src、错误态 |
| ReviewMode | 打开、✅/⭐/❌ 按钮打标、打标自动前进、进度与统计 |
| KeyboardReview | ←/→ 导航、A 保留、D 淘汰、F 收藏、Space 放大、ESC；**快速连按不丢标（队列）** |
| ImageDetail | 信息栏字段、复制 Prompt、设为 Prompt 封面、删除引用保护 |

更新 2 条既有断言（Tabs 文案、Prompt 封面 URL → thumbnail），未删除任何用例；Daily Use 现有用例全保留。

## 四、真机 / 性能 E2E（真实浏览器目检 + 断言）

后端 8002，独立临时 DataRoot（1000 张合成图）：

| 验收项 | 结果（实测数值） |
|---|---|
| 首屏仅 40 张、firstPaint | ✅ cards=40，firstPaint≈1.1s |
| 懒加载占位/已载并存 | ✅ placeholder=12 / loaded=28 |
| 无限滚动加载全部 1000 | ✅ cards=1000，25 次分页、约 972~980 次缩略图请求 |
| 浏览不加载 original | ✅ contentRequests=0 |
| 清理预览/弹窗 | ✅ 候选 100、占用 ~886KB、保护 2 |
| 清理真删 | ✅ deleted=98、protected=2、failed=[]；REJECT→2、total→902 |
| 被删文件/缩略图移除 | ✅；受保护图 original 保留（200/200） |
| Job 审核统计 | ✅ 初始 16/未审16 → 结束 保留5/淘汰11/未审0 |
| 全局 Review 收藏 | ✅ FAVORITE 10→11 |
| 详情复制 Prompt | ✅ 剪贴板含 masterpiece |
| 创建素材 | ✅ GET /assets 核验 source_image_id |
| 设 Prompt 封面 | ✅ GET /prompts 核验 preview_image_id |
| Lightbox 信息栏 + original | ✅ /content 请求、信息栏字段 |
| 滚轮缩放 / 100% / 下一张 | ✅ scale≈2.07、100%、下一张新 original |
| 视觉矩阵 | ✅ 1280×720 / 1440×900 / 1920×1080 Dark；1440×900 Light（应用内切换） |

## 五、未执行 / 部分验证（如实）
- **未真实生成图片**：1000 张与 Job 16 张均为脚本合成图（RTX3060 单张 12–17min，全真实生成不现实）；
  后端生成链路逻辑由现有测试覆盖，本阶段未新增 AI 能力。
- 未在正式 DataRoot（530 张 / 51MB 库）做任何写操作；只读结构核对，未改动。
- 8188 ComfyUI 未启动，未做真实生图 E2E（本阶段范围外）。
