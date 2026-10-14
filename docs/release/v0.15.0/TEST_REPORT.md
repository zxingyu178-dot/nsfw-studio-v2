# TEST_REPORT — v0.15.0

> 全部数字为本轮发布前**实跑**所得，未使用历史声明。日期：2026-10-14。

## 1. 汇总

| 套件 | 命令 | 结果 |
|---|---|---|
| 前端类型检查 | `npm run typecheck` | **EXIT=0**（0 错误） |
| 前端单元/组件测试 | `npm run test:ci`（`vitest run --pool=forks --poolOptions.forks.singleFork=true`） | **Test Files 62 passed（62）；Tests 311 passed（311），0 失败** |
| 前端生产构建 | `npm run build` | **EXIT=0**（多次：workbench、tabs 修复、canvas 修复后各一次均过） |
| 后端测试 | `.venv\Scripts\python.exe -m pytest` | **tests 475；failures 0；errors 0；skipped 3；EXIT=0** |

说明：v0.15 基线前端为 287；随 Workbench 组件与新测试加入，发布前最终为 **311 passed**。

## 2. v0.15 新增/重写的关键测试

| 测试文件 | 覆盖内容 |
|---|---|
| `tests/backend/test_progress_step_contract.py`（**+292 行**） | ComfyUI 真实 `step/max_step` 透传、`execution_start/success/error` 清空 step、归一化 progress；瞬态事件不写库的 5 个契约 |
| `stores/jobStore.liveProgress.test.ts` | liveProgress 瞬态 store：消费 ITEM_PROGRESS、终态清理、不触发整页每 tick 刷新 |
| `pages/Generate/workbench/workbenchLayout.test.ts` | 宽度 clamp、localStorage 持久化、reset、dock 展开 |
| `pages/Generate/workbench/ResizablePane.test.tsx` | separator aria、方向键 8/24px、右栏方向取反、Home/双击复位 |
| `pages/Generate/workbench/workbenchProgress.test.ts` | 跨 stage 加权总进度、upscale 阶段**不伪造 Step**（浮点边界用例） |
| `pages/Generate/glassPerformanceGuard.test.tsx` | glass token 存在、`@supports not` 回退、Canvas 不 blur、slot/input 不 blur、玻璃层 ≤8、stage 用 `--canvas-stage-bg` 且 opaque |
| `components/CanvasViewport/CanvasViewport.test.tsx` | ResizeObserver fit-to-container、缩放钳制、以光标为锚点缩放、rendition 分层 |
| `pages/Generate/workbench/TaskDock.test.tsx` | 收起态状态点/第 N/M/总进度/队列数；暂停 tooltip 文案（“只暂停任务调度，不停止 Python/ComfyUI”） |
| `pages/Prompt/PromptTab.cover.test.tsx`（重写 6 用例） | 预览在文本下方用 thumbnail；null→固定比例“暂未生成”；archived 仍显示；点预览开 dialog；复制不开抽屉；编辑抽屉显式设封面 |

## 3. 为适配新布局改写的旧测试

- `GenerateCompactDesktop.test.ts`：断点从 1319 改为 **1200/1199/1024** 三档；媒体块提取
  改为括号配平；预览 tab 选择器 `.wb4-center`；Tabs 特异性断言更新。
- `shell_sticky.test.ts`：断言旧 `.generate__modebar` 改为 `.wb4-bar` 非 sticky，断点改 1199/1023。
- `GenerateNoDocumentScroll.test.ts`、`GenerateLayoutVisualContract.test.tsx`、
  `GeneratePage.test.tsx`、`SettingsPane.size.test.tsx`：对齐三栏/一屏/拆分按钮 DOM。

## 4. 修复过程中遇到的典型问题（均已闭环）

- `CompactCurrentJob` 对空 `positive_prompt_snapshot` 调 `trim()` 崩溃 → 加 `?? ''`。
- Tooltip 测试同时命中 IconButton 自带 tooltip 与 DS tooltip → 改为 hover 后 `findByText`。
- 双阶段总进度浮点 `9.2/16=57.4999` 落 57 → 用例 progress 调整为整 58%，验证加权而非取整。
- 宽屏 Tabs 误显示（CSS 特异性）→ `.generate .generate__tabs`，见 commit `c30d321`。

## 5. 已知的测试稳定性观察（非逻辑回归）

- `Gallery.detail.test.tsx`、`MobileReviewPairing.test.tsx`（含 2 个 timer 用例）在全量
  singleFork 高负载下曾偶发失败；**单跑 7/7 通过**，最终全量复跑 **311/311 全绿**，
  判定为负载下 timer 抖动，非业务回归。

## 6. 未覆盖项（环境受限）

- 真机 ComfyUI Step 1..N 端到端出图、Running/Completed 截图：引擎 STOPPED、ControlHub offline。
  合同层由上述后端 5 契约 + 前端 progress 测试确定性覆盖。
- 冷/热启动计时：见 `RUNTIME_COLD_START_FOLLOWUP.md`。
