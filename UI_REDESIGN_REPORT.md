# NSFW Studio V2 — UI 重构报告（UI Redesign Report）

- 任务：在后端完全冻结的前提下，对 NSFW Studio V2 前端进行系统化 UI/UX 重构。
- 分支：`feature/ui-v1-redesign`（未自行 merge main）。
- 技术栈：React 18 + TypeScript + Vite + React Router（BrowserRouter）。

---

## 1. 基线与提交

- 基线版本：`v0.8.0`
- 基线 commit：`1b8286be831bdc811b79dc064189a2ba87458053`
- 最终功能 commit：`34b6acf`（feat(ui-5)）
- 提交链（新 → 旧）：

| Commit | 内容 |
|---|---|
| `34b6acf` | feat(ui-5)：清理 app.css 死规则、移除遗留 EmptyState |
| `c7ac114` | feat(ui-4)：迁移素材与设置 |
| `f801b2f` | feat(ui-3)：迁移提示词中心（Prompt / Recipe / History） |
| `ff9c45e` | feat(ui-2)：迁移图库 |
| `5e03962` | feat(ui-1)：迁移生成工作台 |
| `3e349ee` | feat(ui-0)：设计系统、布局基元与应用外壳 |
| `813a336` | docs：IA / 设计系统 / 页面改造清单 |

> 最终的 5 份 `docs/UI_*.md` 与本报告在 `34b6acf` 之后的文档提交中一并交付，最新提交哈希以 `git log -1` 与交付说明为准。

---

## 2. 修改文件

相对基线共变更 60 项（新增 / 修改 / 删除），完整清单：

- 新增设计系统 `frontend/src/components/ui/`：16 类组件（icons、Button、Input、Select、Slider、Switch、Checkbox、RadioGroup〔含 SegmentedControl〕、Tabs、Badge、Progress、Drawer、Modal、Toast、Tooltip、States）、`useOverlay`、`ui.css`、`ui.test.tsx`、`index.ts`。
- 新增布局基元 `frontend/src/components/layout/`：Page、Section、Grid（含 PageHeader / Stack / Divider）与 `layout.css`。
- 外壳：`main.tsx`、`layouts/MainLayout.tsx`、`app/App.tsx`、`app/app.css`。
- 生成页：`pages/Generate/`（GeneratePage、PromptEditorPane、ResultPane、SettingsPane、AssetPickerDrawer、新增 Pane、`generate.css`、测试）；共享 `components/ImagePickerDrawer.tsx`、`components/ComposePreview.tsx`、新增 `components/compose-preview.css`。
- 图库：`pages/Gallery/GalleryPage.tsx`、新增 `gallery.css` 与测试。
- 提示词中心：`pages/Prompt/`（PromptPage、PromptTab、RecipeTab、HistoryTab）、新增 `prompt.css` 与测试。
- 素材 / 设置：`pages/Assets/`（AssetsPage、新增 `assets.css`、测试）、`pages/Settings/`（SettingsPage、新增 `settings.css`、测试）。
- 主题：扩展 `themes/tokens.css`。
- 测试设施：新增 `vitest.config.ts`、`src/test/setup.ts`；更新 `package.json` / `package-lock.json`。
- 删除：零引用的遗留 `components/EmptyState.tsx`；未被引用的 scratch 目录 `pages/Generate/PromptPane/`。
- 文档：新增 `docs/UI_INFORMATION_ARCHITECTURE.md`、`UI_DESIGN_SYSTEM.md`、`UI_PAGE_CHANGE_PLAN.md`、`UI_API_GAP.md`、`UI_ACCEPTANCE.md`、`UI_CHANGELOG.md` 与本报告。

---

## 3. 页面完成情况

| 页面 / 路由 | 状态 | 说明 |
|---|---|---|
| 生成 `/generate` | ✅ | 三栏 5fr:4fr:3fr；结构化八栏顺序不变；模式 / 工作流 / 动态参数 / 尺寸 / 数量 / Seed / 队列 / 任务进度 / 当前图 / 缩略图全部接入真实 Store/API |
| 图库 `/gallery` | ✅ | 筛选 Tabs、网格 / 按任务分组、多选高清、宽详情抽屉、来源 / 派生关系、审图与收藏、创建素材、导入 |
| 提示词 `/prompts` | ✅ | 我的 Prompt / 配方 / 历史三 Tab；卡片 + 宽抽屉编辑、不可变版本、历史两级归组与 Workflow / 缩略图 |
| 素材 `/assets` | ✅ | 分类 Tabs、搜索 / 归档、上传 Modal、详情抽屉、Face 参考图绑定 / 更换 / 移除、版本历史 |
| 设置 `/settings` | ✅ | 主题切换（深色 / 浅色）与关于面板；未新增无后端支撑的开关 |
| 应用外壳 / 导航 | ✅ | 固定品牌与五项导航，右侧 Studio / Engine 两个可区分状态 + 主题切换 |

业务规则保持冻结：Job 状态、Review 状态、结构化八栏、Asset 分类、核心模块、单 Worker 串行、Seed、Pause/Cancel/Resume、Image parent/derived、Recipe 语义均未改变。

---

## 4. 依赖变化

- 运行时依赖（dependencies）：**无变化**（未引入任何第三方 UI 框架 / 动画库，符合合同 §36）。
- 新增开发依赖（devDependencies），仅用于前端测试：
  - `vitest` ^3.2.7
  - `jsdom` ^30.1.2
  - `@testing-library/react` ^16.3.3
  - `@testing-library/jest-dom` ^7.0.1
  - `@testing-library/user-event` ^14.6.7
- 新增脚本：`test`、`test:watch`、`typecheck`。
- 说明：vitest 选用 3.x 而非更新主版本，因其 peer 依赖与当前 Vite 5 匹配（更高版本要求 Vite 6）。

---

## 5. API Gap

- 结论：**No blocking API gaps.** 全部页面在现有 46 个端点契约上完成，未改任何端点 / 字段 / 枚举。
- 记录了 2 条非阻塞观察（派生版本关系前端拼装、无批量审图端点），详见 `docs/UI_API_GAP.md`。

---

## 6. Build

- `npm run build`（`tsc --noEmit` + `vite build`）：✅ 成功。
- `tsc --noEmit` 单独检查：✅ 0 错误。
- 产物：`dist/assets/index.css` 约 42.6 kB、`index.js` 约 262.7 kB（gzip 后 CSS ≈ 7.5 kB / JS ≈ 81.8 kB）。

---

## 7. Test

- Vitest：✅ 6 个测试文件、**44 条用例全部通过**。
  - 设计系统 `ui.test.tsx` 31 条；
  - Generate 2、Gallery 5、Prompt 2、Assets 2、Settings 2。
- 现有 Store 测试（`test:store`）予以保留，未删除任何既有测试。

---

## 8. 浏览器验收

- 以 Headless Chromium 对 dev server 实地截图走查：
  - 生成工作台三栏在 **1280 / 1440 / 1920** 深色下无溢出、比例正确；
  - 五个页面在 **1440 深色**与 **1440 浅色**下渲染正确；
  - 后端离线时正确呈现空态、“请求失败（500）”、Studio / Engine 离线指示与“引擎 离线”。
- 键盘：交互组件具备 `:focus-visible` 焦点环，浮层管理焦点；reduced-motion 降级就位。
- 逐项场景与状态矩阵见 `docs/UI_ACCEPTANCE.md`。

---

## 9. Dark / Light

- ✅ 深色：以深灰 / 黑灰为主体、紫色为强调色，五页面 + 三宽度走查。
- ✅ 浅色：非简单反色，表面 / 边框 / 文本与强调色独立调校，五页面 1440 走查；主题经 `themeStore` 持久化（`nsfw-studio-theme`），切换即时。
- ◐ 浅色在 1280 / 1920 未逐宽截图（同一 Token 对称，风险低）。

---

## 10. 未完成 / 待验收（如实披露）

- 走查时后端未运行，**真实生成与数据写回的端到端路径**（提交、队列流转、Keep/Reject/Favorite 写回、高清、图生图、Resume、Recipe / Prompt 保存、Job failed 实拍）标为 ◐，界面与组件逻辑已验证，需在真实后端环境由主验收按 `docs/UI_ACCEPTANCE.md` 快速复验；真实引擎按合同 §51 至多各跑 1 次文生图 / Img2Img。
- 浅色 1280 / 1920 逐宽截图、键盘 Tab 顺序与 reduced-motion 的实拍未做（CSS / Token 已保证）。
- 大数据量（100 / 更多）的虚拟化在真实规模触发时再引入，当前不过度工程化。

---

## 11. Git 状态

- 工作分支：`feature/ui-v1-redesign`；**未自行 merge main / develop**。
- 交付要求：build GREEN、类型检查 GREEN、44 测试 GREEN、工作树在提交后 clean。
- 提交均推送至 `origin/feature/ui-v1-redesign`（远程仓库 `https://github.com/zxingyu178-dot/nsfw-studio-v2.git`）；推送期间如遇网络临时重置，提交安全保存在本地，网络恢复后补推并以 `git ls-remote` 核对远程 HEAD。
- 未提交 node_modules、dist、真实图片 / DataRoot、数据库、截图大包或任何密钥（截图证据置于 gitignored 的 `handoff/`）。

---

## 12. 结论

在后端、API、数据模型与业务规则完全不动的前提下，已将 v0.8.0 的现有能力重构为统一设计语言、双主题、覆盖 1280 / 1440 / 1920 的桌面级 Web 界面，并以类型检查、44 条组件测试、生产构建与多分辨率 / 双主题截图佐证。分支保持不合并，交由主验收 Agent 按 §55 流程接管。
