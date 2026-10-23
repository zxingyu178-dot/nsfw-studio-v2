# NSFW Studio V2 前端 UI 重做清单（开发交接版）

- 生成时间：2026-10-23
- 对应版本：**v0.36.0**（tag `v0.36.0`，`main = develop = d65b854`）
- 仓库：`D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2`
- 前端目录：`frontend/`
- 用途：作为 UI 全面重做/重构的**现状清单 + 接口边界 + 验收依据**。重做时先读第 10 节「不能动的契约」。

---

## 1. 技术栈与运行方式

| 项 | 值 |
|---|---|
| 框架 | React 18.3 + TypeScript 5.6 |
| 构建 | Vite 5.4（`tsc --noEmit && vite build`） |
| 路由 | react-router-dom 6.26（BrowserRouter，无数据路由） |
| 状态 | 自研 `useSyncExternalStore` store（无 Redux/Zustand/TanStack Query） |
| 样式 | 手写 CSS + CSS 变量（无 Tailwind/CSS Modules/Sass） |
| 测试 | Vitest 3 + Testing Library + jsdom（93 个测试文件 / 442 tests） |
| Node | `>=22.22.2 <23` |
| 运行 | 生产由 FastAPI 直接托管 `frontend/dist`（SPA catch-all）；开发 `npm run dev`（5173，`/api` 代理到 8000） |
| 后端 | FastAPI `/api/v1`，服务固定 `127.0.0.1:8000`（loopback，前端绝不直连 ComfyUI） |

### 常用命令

```powershell
# 开发
cd frontend
npm run dev
# 类型检查
npm run typecheck
# 测试（CI 方式）
$env:CI='true'; node_modules\.bin\vitest.cmd run --pool=forks --poolOptions.forks.singleFork=true
# 生产构建
npm run build
```

发布链路见 `scripts/deploy_app_dist.ps1`（app 实例 pull → build → 同步 dist）与 `scripts/check_app_dist.ps1`；桌面启动器为 `scripts/launch_studio_hidden.vbs`（无控制台窗口）。

---

## 2. 代码规模速览

| 目录 | 文件数 | 行数 |
|---|---:|---:|
| `src/pages` | 125 | 17,264 |
| `src/components` | 75 | 8,072 |
| `src/stores` | 9 | 1,341 |
| `src/api` | 2 | 647 |
| `src/types` | 1 | 740 |
| `src/themes` | 3 | 542 |
| `src/app` | 3 | 374 |
| `src/utils` | 6 | 300 |
| `src/hooks` | 2 | 144 |
| `src/layouts` | 1 | 27 |
| `src/test` | 2 | 92 |
| **合计（ts/tsx/css）** | **231** | **29,571** |

### 最大文件（重做时优先拆分）

| LOC | 文件 |
|---:|---|
| 1327 | `pages/Generate/generate.css` |
| 1063 | `components/ui/ui.css` |
| 882 | `pages/Prompt/prompt.css` |
| 858 | `pages/Prompt/PromptTab.tsx` |
| 818 | `types/workbench.ts` |
| 746 | `pages/Gallery/gallery.css` |
| 681 | `api/client.ts` |
| 640 | `pages/Gallery/GalleryPage.tsx` |
| 533 | `pages/Gallery/ReviewMode.tsx` |
| 529 | `pages/Gallery/components/GalleryDetailDrawer.tsx` |
| 467 | `stores/workbenchStore.ts` |
| 442 | `stores/jobStore.ts` |
| 416 | `pages/Prompt/HistoryTab.tsx` |
| 411 | `themes/tokens.css` |
| 403 | `components/ui/ui3/ui3.css` |
| 392 | `components/EngineControlPopover.tsx` |
| 341 | `pages/Prompt/RecipeTab.tsx` |
| 333 | `pages/Generate/workbench/CanvasStage.tsx` |

---

## 3. 路由与页面地图

入口：`src/main.tsx` → `src/app/App.tsx`（Routes）→ `src/layouts/MainLayout.tsx`（TopNav + `<Outlet/>`）。

| 路由 | 页面文件 | 作用 |
|---|---|---|
| `/` | — | 重定向 `/generate` |
| `/generate` | `pages/Generate/GeneratePage.tsx` | 生成工作台（Workbench 4.0，Canvas First 三栏） |
| `/gallery` | `pages/Gallery/GalleryPage.tsx` | 图库：浏览/审核/批量/导入/清理/大图 |
| `/prompts` | `pages/Prompt/PromptPage.tsx` | 提示词：我的 Prompt / 配方 / 历史 三个 Tab |
| `/assets` | `pages/Assets/AssetsPage.tsx` | 素材库（人脸/服饰/动作/场景） |
| `/settings` | `pages/Settings/SettingsPage.tsx` | 外观/引擎/图片缓存/存储/手机审核/关于 |
| `*` | — | 重定向 `/generate` |

### 顶层导航（`components/TopNav.tsx`）

- 左：品牌 `NSFW Studio`
- 中：生成 / 图库 / 提示词 / 素材 / 设置
- 右：Comfy 状态胶囊（在线/离线）→ 主题切换 → 电源（引擎运行时启停 + 退出 Studio）

### 页面内 Tab / 子视图

| 页面 | 子视图 |
|---|---|
| 生成 | 宽屏三栏；窄屏（<1024）切换 Prompt / 预览 / 配置 三个 Workspace Tab（`GeneratePage` 内 `activeTab`） |
| 图库 | 全部 / 待审核 / 收藏 / 归档；视图「网格 / 按任务查看」；审核模式（全屏 ReviewMode）；详情抽屉；大图 Lightbox；清理废片弹窗 |
| 提示词 | 我的 Prompt / 配方 / 历史 |
| 素材 | 全部 / 人脸 / 服饰 / 动作 / 场景（Tabs） |
| 设置 | 外观、生图引擎、图片缓存、存储、手机审核（MobileReviewSection）、关于 |

---

## 4. 逐页功能清单

### 4.1 全局壳

- `MainLayout`：启动 jobStore（SSE + 兜底轮询）、应用级滚动容器、Generate 页面 `overflow:hidden` 特殊处理。
- `ResumeInterruptedPrompt`（v0.36）：启动检测 `INTERRUPTED` 任务，弹窗「一键继续全部 / 稍后」；「稍后」记 `sessionStorage`。
- `TopNav`：5 个主导航、Comfy 状态胶囊（仅展示，详细操作在电源面板）、主题切换、`PowerMenu`（Engine 启停/Studio 退出）。
- `ThemeProvider` / `themeStore`：dark/light，`data-theme` 驱动 CSS 变量，localStorage `studio.theme`。
- 通用 overlay：`useOverlayScrollLock` 同时锁 html/body/`.app-shell__main`，支持嵌套 ref-count。

### 4.2 生成工作台（`/generate`）

**布局**：`ResizablePane` 左（默认 280，可拖/收起）+ 中画布 + 右（默认 320，可拖/收起）；`WorkbenchBar` 顶部；`TaskDock` 底部收起态常驻。窄屏切换 Workspace Tabs。

| 区域 | 文件 | 关键能力 |
|---|---|---|
| 左 Prompt Console | `workbench/PromptConsole.tsx`、`PromptSlotRow` | 结构化 8 字段（风格/人脸/服饰/动作/场景/构图/光线/额外）+ Negative + Prompt 预览；单槽位聚焦；素材套用/清除；输入图片（图片生成模式）；从提示词库导入（`PromptLibraryDrawer`） |
| 中 Canvas | `workbench/CanvasStage.tsx`、`CanvasViewport`、`ProgressHUD` | 结果画布（zoom-to-cursor / 平移 / Fit / 100%）、实时进度 HUD、filmstrip 缩略图、←/→ 切换、收藏/保留/淘汰、Lightbox |
| 右 Inspector | `workbench/InspectorPanel.tsx` | 工作流模块选择（PopoverSelect，含不可用 warning）、比例/分辨率（AspectRatioPicker）、数量（NumberStepper）、Seed（随机/固定）、高清放大开关、高级参数折叠、`SplitGenerateAction`（生成 N 张 / ⚡ 插队） |
| 顶 Bar | `workbench/WorkbenchBar.tsx` | 模式/来源/重置/「保存 ▾」（保存为 Prompt / Recipe）、导入配置 |
| 底 TaskDock | `workbench/TaskDock.tsx` + `components/QueuePanel.tsx` | 收起态：状态/第 N 张/总进度/队列数/暂停后续；展开态：当前任务 + 队列全部操作（暂停/继续/取消/插队/清空/拖拽排序） |
| 快捷键 | `SplitGenerateAction`、`CanvasStage` | Ctrl/Cmd+Enter 提交；←/→ 切图；Esc 关闭 overlay（Lightbox/弹窗） |

**数据来源**：`moduleApi.list()`（能力目录，`available=true` 是 Gate）、`imageApi`（输入图/素材/结果）、`jobApi`（提交/队列）、SSE `/api/v1/events/jobs` + `/jobs` 回源。

### 4.3 图库（`/gallery`）

- 顶部两层 Toolbar（`GalleryToolbar`）：
  - 第一层：全部/待审核/收藏/归档 Tabs；网格 / 按任务切换。
  - 第二层：审核状态细分、来源（全部/ComfyUI/导入）、排序（最新优先/最早优先/评分）、网格密度（小/中/大）；开始审核、选择、导入、**删除淘汰图**、更多（清理废片、统计？）。
- 网格：`GalleryGrid`（flex 列 masonry，`distributeColumns` 按图片真实宽高分配；ResizeObserver 自适应列数；无 CSS column 抖动）。
- 卡片：`GalleryCard`（真实宽高比占位、审核状态/导入徽章、收藏）。
- 审核模式：`ReviewMode`（全屏，键盘操作，审核会话分页/一致队列；`reviewSessionApi`）。
- 多选：`GallerySelectionBar`（全选当前筛选、高清放大、保留、淘汰、归档、**删除**、收藏、取消选择）。
- 详情抽屉：`GalleryDetailDrawer`（元信息、版本、审核/收藏、用作输入、创建素材、设封面、溯源、危险区：淘汰 / 仅 REJECT 永久删除）。
- 大图：`ImageLightbox` + `LightboxInfoPanel`（缩放/平移、信息面板可隐藏、键盘）。
- 批量审核：保留/淘汰/归档（chunked，>100 带 ConfirmModal）、批量收藏、**清理废片**（`CleanupRejectedDialog`，预览可删/受保护/释放空间）。
- 导入：多文件导入（进度、sha256 去重、导入后跳转）。
- 分页：`useGalleryQuery`（筛选参数、stats、列表、load more）；偏好 localStorage：`gallery.density`、`gallery.fit`、`lightbox.infoHidden`。

### 4.4 提示词（`/prompts`）

#### 我的 Prompt（`PromptTab`，v0.35 起整行列表）

- 工具栏：搜索（名称/内容）、显示已归档、排序（最近更新/评分高→低/评分低→高）、状态（全部/保留/候选/已淘汰）、评分（全部/仅已评分/仅未评分）、新建 Prompt。
- 列表：**一行一段 Prompt**；标题 + 状态/评分 + 摘要（≤2 行）+ 对应生成图（最多 3 张缩略图 + `+N`）+ 操作（使用/复制/编辑/评分/收藏/删除）。
- 数据：`promptApi.list({include_images, images_limit, include_evaluation})`、`useInfiniteList` 分页；URL 同步筛选（`useSearchParams`）；筛选偏好 `prompt.filters.v1`。
- 新建/编辑 Drawer：结构化 8 字段 / 全文模式切换、Negative、Prompt 预览（`ComposePreview`）、封面图选择（`ImagePickerDrawer`）、版本历史。
- 评分：`PromptScoringDialog`（单项评分 + 总分），`promptApi.createEvaluation/listEvaluations`。
- 删除：软删除确认（`promptApi.archive`，可在「显示已归档」找回）；notice 提示。

#### 配方（`RecipeTab`）

- 列表/搜索/显示归档；Drawer 查看版本历史；「在生成工作台打开」→ `navigate('/generate', {state:{workbench}})`；`useInfiniteList` 分页。

#### 历史（`HistoryTab`）

- 任务族两级归组：原任务 + 续跑任务；bucket：全部/进行中/已完成/失败/已取消；来源筛选（web/resume/agent/doubao）。
- 卡片：状态、来源、续跑标记、Prompt 摘要、完成数、pipeline；详情 Drawer：完整 Prompt/结构化字段/尺寸/Seed/Workflow stages/版本/错误/生成图片；操作：在生成工作台打开、图库查看、**继续剩余图片**。
- v0.36：工具栏「继续全部中断任务」按钮。

### 4.5 素材（`/assets`）

- Tabs：全部 / 人脸 / 服饰 / 动作 / 场景；搜索；无限加载。
- `AssetGrid` / `AssetCard`；`AssetDetailDrawer`（元信息、版本、归档/恢复、在生成工作台使用）；`AssetEditor`（新建/编辑、结构化描述、图片绑定、版本）。
- API：`assetApi`（list/get/create/updateMeta/addVersion/listVersions/archive/restore/workbench）。

### 4.6 设置（`/settings`）

| 区块 | 功能 |
|---|---|
| 外观 | 深色/浅色（RadioGroup，`themeStore`） |
| 生图引擎 | 状态展示（STOPPED/STARTING/RUNNING_MANAGED/RUNNING_EXTERNAL/STOPPING/PORT_CONFLICT/ERROR）、启动/停止/重启（`engineRuntimeApi`） |
| 图片缓存 | 缩略图/预览回填 启动/停止/进度（`imageApi.startBackfill/backfillStatus/stopBackfill`） |
| 存储 | DataRoot 磁盘剩余空间、阈值 Warning 10GB / Severe 5GB、路径/容量只读展示 |
| 手机审核 | `MobileReviewSection`：8767 Bridge 状态/启停、生成 6 位一次性配对码（10 分钟倒计时）、已配对设备列表/撤销；红线：不改防火墙 |
| 关于 | 版本/说明 |

---

## 5. 公共组件清单

### 5.1 `components/ui`（主设计系统）

`index.ts` 导出：

- 基础：`Button`、`Input`、`Select`、`Slider`、`Switch`、`Checkbox`、`RadioGroup`
- 容器/导航：`Tabs`/`TabPanel`、`Drawer`、`Modal`/`ConfirmModal`、`Tooltip`
- 展示：`Badge`、`StatusBadge`、`Progress`、`Spinner`、`EmptyState`、`ErrorState`（`States.tsx`）、`ElapsedTimer`
- 图标：`icons.tsx` 统一图标集
- 样式：`ui.css`（1063 LOC）

### 5.2 `components/ui/ui3`（第二套紧凑控件，重构时需合并/替换）

`ActionButton`、`ActionDock`、`ChoiceGrid`、`ChoiceTile`、`DisclosureButton`、`IconButton`、`NumberStepper`、`PopoverSelect`、`PowerButton`、`StatusPill`、`ToolbarIcon`、`Tooltip`（独立实现）、`icons`、`ui3.css`（403 LOC）。

> 现状：主 UI 以 `ui` 为主，但 `TopNav`、`PromptConsole`、`CanvasStage`、`TaskDock`、`InspectorPanel` 已在使用 `ui3`。**两套设计系统并存是本次重做最主要的清理点之一**。

### 5.3 业务通用组件

`TopNav`、`ThemeToggle`、`PowerMenu`/`PowerControl`、`EngineControlPopover`（引擎完整运行时面板）、`ImageLightbox`、`LightboxInfoPanel`、`ImagePickerDrawer`、`ComposePreview`、`CanvasViewport`（`components/CanvasViewport`）、布局 `PageContainer`（`components/layout/Page`）。

### 5.4 已知未被引用/疑似遗留（重做时先确认再删）

静态引用扫描（不含测试）发现以下文件当前没有生产引用：

- `components/EngineStatus.tsx`
- `components/layout/Grid.tsx`
- `components/layout/Section.tsx`
- `pages/Generate/components/CurrentJobCard.tsx`
- `pages/Generate/components/GenerateAction.tsx`
- `pages/Generate/PromptEditorPane.tsx`
- `pages/Generate/SettingsPane.tsx`
- （`main.tsx` 为入口，扫描误报）

另外 `pages/Generate/Pane.tsx` 仍有引用（`InspectorPanel`），不是纯遗留。

---

## 6. 状态与数据流

### 6.1 `stores/jobStore.ts`（442 LOC）

- 全局任务/队列/引擎状态；`useSyncExternalStore`。
- **SSE 只做实时通知**（`/api/v1/events/jobs`），任何事件都回源 `GET /jobs`、`/queue`、`/engine/status`；断线兜底轮询。
- `trackedJob`（本页提交/关注 Job）、`liveProgressByStageItem`（瞬态进度，按 **stage_item_id** 索引，避免 basic/upscale 串进度）。
- 动作：提交、暂停/继续/取消、`resumeRemaining`、`resumeInterrupted`、队列暂停/继续/拖拽排序/清空、引擎状态。
- `busyJobId` + `busyJobAction` 精确禁用按钮。

### 6.2 `stores/workbenchStore.ts`（467 LOC）

- `WorkbenchSnapshot` 单一事实源：promptMode、structured（8 字段）、fullPrompt、negative、selectedAssets、inputImages、尺寸/数量/Seed、workflowModules、moduleCatalog、sourcePrompt/Recipe。
- 生成模式 text/image；Primary Module Gate（`available=true`）；`hydrateWorkbench`（从 Prompt/Recipe/History/Image 恢复）、`resetWorkbench`。
- 参数偏好 `generate.params.v1`（只存尺寸/数量/Seed 模式，不存 Prompt）。

### 6.3 其他

- `stores/themeStore.ts` + `themes/ThemeProvider.tsx`：主题。
- `stores/workbenchPrefs.ts`：参数偏好。
- `pages/Generate/workbench/workbenchLayout.ts`：左右栏宽度/收起/TaskDock 开合（localStorage）。
- `pages/Gallery/hooks/*`：`useGalleryQuery`（列表/stats/筛选/分页）、`useGallerySelection`、`useGalleryPrefs`、`useReviewSession`。
- `pages/Prompt/useInfiniteList.ts`：无限加载通用 hook。
- `components/ResumeInterruptedPrompt.tsx`：启动恢复弹窗（v0.36）。

### 6.4 localStorage / sessionStorage 键

| Key | 用途 |
|---|---|
| `studio.theme`（见 themeStore） | 主题 |
| `generate.params.v1` | 工作台尺寸/数量/Seed 偏好 |
| `workbench.leftWidth` / `workbench.rightWidth` / `workbench.leftCollapsed` / `workbench.rightCollapsed` / `workbench.taskDockOpen` | 工作台布局 |
| `prompt.filters.v1` | Prompt 筛选 |
| `gallery.density` / `gallery.fit` | 图库密度/适应方式 |
| `lightbox.infoHidden` | Lightbox 信息栏 |
| `resume-interrupted-dismissed`（sessionStorage） | 启动恢复弹窗「稍后」 |

---

## 7. API 客户端清单（`src/api/client.ts`，681 LOC）

所有调用统一 `request()`（`/api/v1`，JSON、错误 `ApiRequestError`）。DTO 定义在 `src/types/workbench.ts`（与后端 schema 字段名镜像）。

| 域 | 方法 |
|---|---|
| `promptApi` | list, get, create, updateMeta, addVersion, listVersions, restoreVersion, archive, restore, setPreviewImage, clearPreviewImage, compose, createEvaluation, listEvaluations, setStatus |
| `assetApi` | list, get, create, updateMeta, addVersion, listVersions, archive, restore, workbench |
| `recipeApi` | list, get, create, updateMeta, addVersion, listVersions, restoreVersion, archive, restore |
| `jobApi` | create, list, get, pause, resume, cancel, resumeRemaining, resumeInterrupted, queue, reorder, pauseQueue, resumeQueue, clearStale, engineStatus |
| `imageApi` | list, ids, stats, get, review, favorite, setStatus, preview, batchStatus, cleanupRejected, jobGroups, startBackfill, backfillStatus, stopBackfill, workbench, jobSummary, upscale, versions, provenance, importFiles, references |
| `moduleApi` | list（WorkflowModule + ParameterSpec + `available`/`size_mode`） |
| `historyApi` | list（任务族分页） |
| `engineRuntimeApi` | get, start, stop, restart（ComfyUI 生命周期，唯一 owner=ControlHub） |
| `systemApi` | status, requestShutdown |
| `mobileReviewApi` | runtime, start, stop, restart, createPairingCode, devices, revokeDevice |
| `reviewSessionApi` | createSession, latestSession, queuePage, decide, reportPosition, complete |

额外：`subscribeJobEvents`（SSE）、图片 URL 辅助函数（`imageThumbUrl` / `imagePreviewUrl` / `imageContentUrl`，定义在 types）。

---

## 8. 设计系统与样式

- `themes/tokens.css`（411 LOC）：颜色/间距/圆角/阴影/字号等 CSS 变量；`ThemeProvider` 通过 `data-theme` 切换 dark/light。
- `app/app.css`（299）、`components/layout/layout.css`（189）、`components/ui/ui.css`（1063）、`ui3/ui3.css`（403）。
- 页面级 CSS：`generate.css`（1327）、`prompt.css`（882）、`gallery.css`（746）、`assets.css`（198）、`settings.css`（139）、`review-mode.css`（107）；组件级：`CanvasViewport.css`、`ImageLightbox.css`、`LightboxInfoPanel.css`、`EngineControlPopover.css`、`PowerMenu.css`、`compose-preview.css`。
- 设计规范：`docs/DESIGN.md`（暗色优先、哑光、1px 分隔、6–8px 圆角、零重阴影、Glass 等）。
- 守卫测试：`themes/design_tokens.test.ts` 要求所有无 fallback 的 `var()` 必须有全局 token 或白名单；`noBom.test.ts` 禁止 BOM；`legacy.guard.test.ts` 约束旧组件。
- 响应式：≥1200 可调三栏；1024–1199 固定紧凑；<1024 Workspace Tabs（由 CSS + GeneratePage 决定）。

---

## 9. 测试与质量现状

- 测试文件：93 个；用例：442（最近全量通过）。
- 分布：`pages/Generate/workbench` 15、`pages/Generate` 12、`pages/Gallery` 12、`pages/Prompt` 11、`components/__tests__` 8、`ui/ui3` 6、`stores` 5、`Settings` 3、其他少量。
- 测试重点：工作台布局/参数/快捷键/进度、图库筛选/选择/清理/比例、Prompt 列表/筛选/评分/删除、History 分页/续跑、设置、设计 token、SSE store。
- 命令：`npm run build`（tsc + vite）必须通过；CI 运行前端测试 + 构建。
- 人工验收辅助：项目内曾用 CDP（Chrome DevTools Protocol）脚本做真实页面截图/网络计时/交互验证；临时脚本放在 `temp/`，不提交。

---

## 10. 重做时**不能动**的契约（硬边界）

1. **后端 API 与 DTO 字段名**：`types/workbench.ts` 与 `backend/app/schemas` 双侧镜像，字段名不得另起；前端不得直接拼非 `/api/v1` 路径。
2. **WorkbenchSnapshot 结构**：`prompt_mode` / `structured_prompt`（8 字段顺序固定）/ `full_prompt` / `negative_prompt` / `selected_assets` / `input_images` / `generation_mode` / 尺寸数量 Seed / `workflow_modules`（含 config / 执行身份）——改变会导致历史恢复/配方/Job 快照不兼容。
3. **工作流能力 Gate**：`moduleApi.list()` 的 `available=true` 是唯一依据；`size_mode` / ParameterSpec 由后端下发，前端不得硬编码参数范围。
4. **执行架构**：前端 → Studio `/api/v1` → ControlHub/ComfyUI；**前端绝不直连 8188**，不自行启动引擎（引擎操作只经 `engineRuntimeApi` → ControlHub）。
5. **SSE 语义**：事件只是通知，Job/Queue 状态必须回源 `GET`；不要在前端自建第二事实源。
6. **图片语义**：缩略图/预览/原图 URL 统一走后端；删除是「淘汰（REJECT）→ 清理废片」，普通 UI 不做物理删除；Prompt 删除是软删除（归档）。
7. **本地存储键**：重做时若改 key 名需迁移旧数据（`generate.params.v1`、`workbench.*`、`prompt.filters.v1`、`gallery.*`、`lightbox.infoHidden`、`studio.theme`）。
8. **运行边界**：8000 只绑 loopback；生产静态托管 dist；launcher 无控制台窗口；不写 BOM；不提交 DataRoot/密钥。

---

## 11. 已知痛点/技术债（重做优先级参考）

### 高优先级
- **两套设计系统并存**（`ui` + `ui3`），同类控件重复，视觉与交互不一致；
- 页面/样式文件过大（`PromptTab` 858、`GalleryPage` 640、`generate.css` 1327、`prompt.css` 882），改一处容易牵连；
- 弹窗/提示/错误态各自实现（Modal/Confirm/notice/toast 混用），缺统一交互规范；
- 图库/提示词列表均为「全量渲染 + 加载更多」，无虚拟滚动；图片多时首屏开销大；
- 响应式只做「三栏折叠」，移动/中等宽度体验未系统设计；
- 无障碍（focus trap、aria、键盘）只覆盖部分组件/页面。

### 中优先级
- 无组件目录/Storybook，组件用法靠读源码；
- 大量页面级 `useEffect` 拉数据 + 手写 loading/error，重做可抽数据 hooks；
- 图标两套（`ui/icons` 与 `ui3/icons`）；
- 视觉细节（密度、间距、字体层级）散落在各页 CSS，不统一；
- 历史/队列/续跑等状态展示分散在 TopNav、TaskDock、HistoryTab、Canvas 多处。

### 低优先级/清理
- 第 5.4 节列出的疑似遗留文件；
- 部分测试依赖实现细节（class 名、文案），重做时需同步更新；
- 无 Playwright/E2E 视觉回归（当前靠 CDP 手工脚本）。

---

## 12. 建议的重做顺序（减少返工）

1. **设计系统单源**：确定一套 primitives（Button/Input/Select/Tabs/Modal/Drawer/Toast/Tooltip/States/Icon），统一 token；合并 ui/ui3。
2. **应用壳**：TopNav、MainLayout、Theme、Power/Engine 面板、全局 overlay 与滚动策略。
3. **数据层适配**：保留 `api/client.ts` 与 DTO 类型不动，在其上抽 hooks（列表分页、Job/SSE、工作台快照），避免重写业务契约。
4. **Prompt 页**（列表 + 详情/评分/删除）→ **历史页**（任务族/续跑）→ **图库**（网格/审核/选择/清理/大图）→ **生成工作台**（三栏 + Canvas + TaskDock）→ **素材/设置**。
5. 每完成一页，跑该页测试 + `tsc` + `vite build`，并按第 13 节验收。

### 建议新增（不改后端）
- 组件目录（即使不引入 Storybook，也可用静态页）；
- 统一 `useAsyncList` / `useJobTracking` hook；
- 列表虚拟化（图库/提示词）；
- 统一 Notice/Toast/Confirm 语义与键盘支持；
- 设计 token 视觉回归截图（可用现有 CDP 方式固化）。

---

## 13. 重做验收清单（功能 parity）

### 全局
- [ ] 5 个导航路由可达；刷新/直达不 404（SPA fallback）
- [ ] 主题切换持久化；Comfy 状态胶囊正确；电源面板可启停引擎/退出
- [ ] 启动时若有中断任务，出现「一键继续全部」；稍后本次会话不再弹
- [ ] 所有 overlay 打开时背景不滚动，Esc 可关，焦点不跑丢

### 生成工作台
- [ ] 三栏可拖拽/收起，窄屏 Workspace Tabs 可用
- [ ] 结构化 8 字段 + 全文模式切换；Negative；素材套用/清除；输入图（图片生成）
- [ ] 工作流模块选择受 availability Gate；比例/尺寸/数量/Seed/高清参数正确提交
- [ ] 提交、插队、暂停/继续/取消、队列拖拽、清空；SSE 断线后状态可恢复
- [ ] Canvas：进度/第 N 张/阶段、Fit/100%、缩放平移、filmstrip、←/→、收藏/保留/淘汰
- [ ] 保存为 Prompt / Recipe；历史恢复完整执行身份

### 图库
- [ ] Tabs/筛选/排序/密度/视图切换；分页/加载更多；统计数正确
- [ ] 审核模式完整（键盘、批量、撤销 Ctrl+Z）
- [ ] 选择：全选当前筛选、批量保留/淘汰/归档/删除/收藏、chunked 进度
- [ ] 清理废片：预览数量/释放空间/受保护列表/确认删除/刷新
- [ ] 导入：去重、进度、错误可见；详情抽屉与大图所有动作

### 提示词
- [ ] 我的 Prompt：搜索/排序/状态/评分筛选 + URL 同步 + 偏好记忆
- [ ] 整行列表、生成图缩略图 +N、使用/复制/编辑/评分/收藏/删除（软删除可恢复）
- [ ] 新建/编辑 Drawer：结构化/全文、Preview、封面、版本历史
- [ ] 配方：列表/版本/在工作台打开
- [ ] 历史：任务族归组、bucket/来源筛选、详情抽屉、继续剩余、继续全部中断任务

### 素材/设置
- [ ] 素材 5 Tabs、搜索、新建/编辑/版本/归档/在工作台使用
- [ ] 设置：主题、引擎状态与启停、缓存回填进度、存储空间、手机审核配对/设备、关于

### 工程
- [ ] `npm run build` 通过（含 `tsc --noEmit`）
- [ ] 全量 Vitest 通过（或等价覆盖）；新增/修改测试同步更新
- [ ] 无 BOM；无新增未登记依赖；不破坏设计 token 守卫
- [ ] 部署实例 build/check PASS、浏览器强刷后 UI 正常

---

## 14. 参考文件

- `docs/DESIGN.md`：视觉规范
- `docs/API_PLAN.md`：API 契约
- `docs/JOB_STATE_MACHINE.md`、`RECOVERY_SPEC.md`：任务/恢复语义
- `AGENTS.md` §3/§4：项目阶段与架构红线
- `CHANGELOG.md`：逐版行为变更（v0.35 图库删除 / v0.36 一键继续）
- `scripts/deploy_app_dist.ps1`、`scripts/check_app_dist.ps1`：部署/校验
- 当前运行截图：可由启动器打开 `http://127.0.0.1:8000` 后捕获（生成/图库/提示词/设置）
