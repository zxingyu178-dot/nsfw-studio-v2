# GIT_COMMITS — v0.15.0

- 仓库：`https://github.com/zxingyu178-dot/nsfw-studio-v2.git`
- 分支：`feature/v0.15-workbench-layout4`
- 基线：`b974ffa`（`main`，tag `v0.14.1`）
- 统计：相对基线 **47 files changed, 4137 insertions(+), 1198 deletions(-)**

## 提交链（旧 → 新）

| Hash | 时间 | 提交 |
|---|---|---|
| `e93446e` | 2026-10-14 16:15 | `ci: run frontend vitest in PR gate` |
| `af8e940` | 2026-10-14 16:28 | `refactor(progress): split transient progress from persisted events` |
| `b0cdbb8` | 2026-10-14 16:34 | `feat(store): live transient progress state` |
| `666d1c8` | 2026-10-14 17:29 | `feat(canvas): promote CanvasViewport to production` |
| `4b9e899` | 2026-10-14 17:29 | `feat(ui): glass surface tokens/primitives + performance guard` |
| `b1d400e` | 2026-10-14 17:30 | `feat(workbench): Workbench 4.0 canvas-first shell, resizable panes, task dock, progress HUD` |
| `bd9264c` | 2026-10-14 17:31 | `feat(prompt-library): visual preview cards (preview below text, 暂未生成 placeholder)` |
| `c30d321` | 2026-10-14 18:08 | `fix(workbench): hide wide-screen workspace tabs and keep canvas dark matte` |

> 发布提交 `chore(release): v0.15.0`（版本号 bump + CHANGELOG）与 tag **`v0.15.0`**
> 在 docs 提交之后创建；以 tag `v0.15.0` 为发布稳定引用（`git rev-parse v0.15.0`）。

## 各提交内容要点

- **e93446e（CI）**：`.github/workflows/ci.yml` PR 闸门加入前端 `npm run test:ci`；
  `package.json` 增加 `test:ci`（vitest run，singleFork）。
- **af8e940（事件分流）**：`JobService.publish_transient_event` 只发 SSE 不写 `job_events`；
  `queue_worker` 每轮发瞬态 `ITEM_PROGRESS`，仅签名变化/节流/切 stage 才落库。
  （提交标题为 split transient，同提交含真实 step/max_step 透传的后端改动。）
- **b0cdbb8（前端 store）**：`jobStore.liveProgressByItem` 内存瞬态层 + 消费 ITEM_PROGRESS +
  终态清理；新增 `jobStore.liveProgress.test.ts`。
- **666d1c8（Canvas）**：`components/CanvasViewport/` 从 `proto/` 提升为正式组件
  （组件 + css + geometry + 测试）。
- **4b9e899（Glass）**：`themes/tokens.css` 新增 glass token 与 `.glass/.glass--strong`、
  `@supports not` 回退；新增 `glassPerformanceGuard.test.tsx`。
- **b1d400e（Workbench）**：`workbench/` 全部组件（Shell、ResizablePane、WorkbenchBar、
  PromptConsole、InspectorPanel、SplitGenerateAction、TaskDock、CanvasStage、ProgressHUD、
  workbenchLayout/workbenchProgress）、GeneratePage 接入、generate.css 重构与死 CSS 清理、
  旧布局/骨架/一屏测试改写、删除 `proto/` 与两个已迁移测试。
- **bd9264c（Prompt 库）**：`PromptTab.tsx` 卡片预览在下、暂未生成占位、显式操作按钮；
  `prompt.css` 预览/modal 样式；`PromptTab.cover.test.tsx` 重写 6 用例。
- **c30d321（修复）**：宽屏 Tabs 特异性修复（`.generate .generate__tabs`）；Canvas 两主题
  恒定深色哑光（`--canvas-stage-*` token）；同步更新 CompactDesktop 与 glass guard 断言。

## 变更文件清单（A 新增 / M 修改 / D 删除）

- 后端：`engine/base.py`、`engine/comfyui.py`、`services/job_service.py`、
  `workers/queue_worker.py`；新增 `tests/backend/test_progress_step_contract.py`。
- 前端新增：`components/CanvasViewport/*`（4）、`pages/Generate/workbench/*`（15，含 4 测试）、
  `stores/jobStore.liveProgress.test.ts`、`pages/Generate/glassPerformanceGuard.test.tsx`。
- 前端修改：`GeneratePage.tsx`、`SettingsPane.tsx`、`PromptEditorPane.tsx`、
  `pages/Prompt/PromptTab.tsx`、`prompt.css`、`generate.css`、`themes/tokens.css`、
  `stores/jobStore.ts`、`package.json`、CI、多个页面测试。
- 删除：`pages/Generate/proto/`（2 文件，已提升为正式组件）、
  `SettingsPane.compact.test.tsx`、`SettingsPane.queue.test.tsx`（职责已迁移，被新测试覆盖）。

## 未提交（刻意排除，非遗漏）

以下为机器/本地产物，**不纳入提交**：

- `control-hub.json`
- `runtime/`
- `docs/NSFW_资源调查报告.md`
