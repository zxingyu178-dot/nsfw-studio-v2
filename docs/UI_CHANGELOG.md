# UI Changelog

> 分支：`feature/ui-v1-redesign`
> 基线：v0.8.0 / `1b8286be831bdc811b79dc064189a2ba87458053`
> 原则：仅重构前端表现层与交互；后端、API、数据模型、业务规则一律冻结。
> 类前缀约定：设计系统 `ds-`；工作台 `wb-`；图库 `gal-`；提示词中心 `pp-`；素材 `as-`；设置 `st-`。

---

## 规划（commit `813a336`）

- 新增 `docs/UI_INFORMATION_ARCHITECTURE.md`：信息架构、导航与路由、页面职责。
- 新增 `docs/UI_DESIGN_SYSTEM.md`：视觉语言、Token、组件清单。
- 新增 `docs/UI_PAGE_CHANGE_PLAN.md`：逐页改造清单与迁移顺序。

---

## UI-0 — Design System + App Shell（commit `3e349ee`）

- 扩展 `src/themes/tokens.css`：
  - 语义状态色 success / danger / warning / info 及成对弱底色；
  - 三级 surface、字号 / 行高、间距、圆角、阴影、z-index、动效时长；
  - 统一焦点环 `--focus-ring`；`prefers-reduced-motion` 降级。
- 新增 `src/components/ui/`（`ds-` 前缀）：
  - icons、Button、Input（含 Textarea、Field）、Select、Slider、Switch、Checkbox、
    RadioGroup（含 SegmentedControl）、Tabs（含 TabPanel）、Badge（含 StatusBadge）、
    Progress（ProgressBar + Spinner）、Drawer、Modal（含 ConfirmDialog）、Toast（含 Provider/useToast）、
    Tooltip、States（EmptyState / ErrorState / Skeleton）、useOverlay。
  - 配套 `ui.css` 与组件测试 `ui.test.tsx`。
- 新增 `src/components/layout/`：Page / PageHeader / Section / Grid / Stack / Divider 与 `layout.css`。
- 外壳改造：
  - `main.tsx` 引入 tokens / ui / layout 样式并挂载 ToastProvider；
  - `MainLayout` 主区使用 `app-shell__main`；
  - `App.tsx` 以统一页面容器按路由包裹 wide / normal。
- 测试设施：加入 Vitest 3 + Testing Library + jsdom（`vitest.config.ts`、`src/test/setup.ts`）。

---

## UI-1 — Generate 生成工作台（commit `5e03962`）

- 迁移 `GeneratePage`：保留 `location.state` 的水合 / 重置逻辑；模块目录来自 `/modules`，并保留图片生成可用性 Gate。
- 迁移真实使用的编辑器 `PromptEditorPane.tsx`（结构化八栏顺序不变 + 完整 Prompt 模式 + Negative + 输入图片区）。
- 迁移 `ResultPane`（当前结果舞台、缩略图条、跳转图库）、`SettingsPane`（引擎 / 工作流、动态参数、尺寸、数量、Seed、生成、队列与任务进度）、`AssetPickerDrawer`。
- 新增共享 `ImagePickerDrawer`、`ComposePreview`（含独立 `compose-preview.css`）与面板容器 `Pane.tsx`。
- 工作台样式集中于 `pages/Generate/generate.css`（`wb-` 前缀）：三栏 5fr : 4fr : 3fr，窄屏（≤1100px）退单列。
- 新增 `GeneratePage.test.tsx`。
- 清理：删除未被引用、引用了不存在 store 的 scratch 目录 `pages/Generate/PromptPane/`。

---

## UI-2 — Gallery 图库（commit `ff9c45e`）

- 重写 `GalleryPage`，新增 `pages/Gallery/gallery.css`（`gal-` 前缀）。
- 筛选（全部 / 未审核 / 保留 / 收藏 / 淘汰）使用 ds Tabs；选择 / 按任务查看 / 导入使用 ds Button。
- 多选高清工具条（Badge + Button）；图片网格卡片，角标 HD / 选中 / 收藏，状态用 StatusBadge。
- 按任务分组视图；详情使用宽 Drawer：大图预览、来源 / 派生版本链接、保留 / 淘汰 / 收藏操作、溯源字段、折叠的高级信息、创建素材表单。
- 新增 `GalleryPage.test.tsx`（5 条）。

---

## UI-3 — Prompt / Recipe / History（commit `f801b2f`）

- 迁移提示词中心，新增 `pages/Prompt/prompt.css`（`pp-` 前缀）。
- `PromptPage` 页签使用 ds Tabs + TabPanel。
- PromptTab：搜索、显示归档、新建、卡片网格、宽抽屉编辑（结构化 / 完整切换、字段、ComposePreview、版本历史）。
- RecipeTab：配方卡片 + 抽屉（不可变版本快照、素材与输入图快照）。
- HistoryTab：时间桶 Tabs、来源筛选、原任务 + 续跑两级归组、详情抽屉（字段、Workflow 阶段、生成图缩略图）。
- 新增 `PromptPage.test.tsx`（2 条）。

---

## UI-4 — Assets / Settings（commit `c7ac114`）

- 素材：`AssetsPage` 类型 Tabs、搜索 / 归档工具条、卡片网格、上传 Modal、详情 Drawer
  （预览、操作、字段、Face 参考图绑定 / 更换 / 移除、编辑、版本历史）；新增 `pages/Assets/assets.css`（`as-` 前缀）。
- 设置：`SettingsPage` 主题 RadioGroup（包 ThemeProvider）与关于面板；新增 `pages/Settings/settings.css`（`st-` 前缀）。
- 新增 `AssetsPage.test.tsx`（2 条）、`SettingsPage.test.tsx`（2 条）。

---

## UI-5 — Polish + Tests（commit `34b6acf`）

- 裁剪 `src/app/app.css` 死规则：仅保留仍被引用的骨架、顶部导航、Engine 指示、主题切换、通用辅助规则（约 -1426 行）。
- 移除零引用的遗留组件 `src/components/EmptyState.tsx`（已由 ds EmptyState 取代）。
- 全场景走查：
  - 生成工作台三栏在 1280 / 1440 / 1920 深色下截图核验；
  - 五个页面在 1440 深色、1440 浅色下截图核验；
  - 焦点环覆盖全部交互组件，reduced-motion 路径就位。
- 最终验证：`tsc --noEmit` 0 错、Vitest 44 条全部通过、生产 build 成功。
