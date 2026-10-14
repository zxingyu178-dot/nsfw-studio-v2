# WORKBENCH_LAYOUT4_REPORT — v0.15.0（Canvas First 三栏 + 任务坞）

## 1. 布局结构

```
┌──────────────────────── TopNav（glass） ────────────────────────┐
├────────────────────── WorkbenchBar（glass） ────────────────────┤
│ 文生图/图片生成 · 来源上下文 · 重置 · 保存（Prompt/配方）          │
├──────────┬───────────────────────────────────┬───────────────────┤
│ Prompt   │                                    │  参数 Inspector    │
│ Console  │           Canvas（深色哑光）        │  （只负责怎么生成） │
│ (8 槽位)  │     最大视觉区 / 滚轮缩放 / 拖拽     │                   │
│          │                                    │                   │
├──────────┴───────────────────────────────────┴───────────────────┤
│ TaskDock（底部常驻；当前 Job / 队列）                              │
└──────────────────────────────────────────────────────────────────┘
```

- 中栏 Canvas **宽于左右栏**，是视觉中心。
- 左右栏内部滚动，**document 零纵向滚动**。

## 2. 三档断点（`workbenchLayout.ts` + generate.css）

| 视口宽度 | 左栏 | 右栏 | 拖拽手柄 | 布局形态 |
|---|---|---|---|---|
| **≥1200** | 可调 280–420（默认 320） | 可调 270–380（默认 300） | 显示 | 三栏同屏 |
| **1024–1199** | 固定 280 | 固定 270 | 隐藏 | 三栏紧凑 |
| **<1024** | — | — | — | **Workspace Tabs**（Prompt/预览/配置，一次一个 pane） |

- 宽度经 CSS 变量 `--left-w` / `--right-w` 注入。
- 宽度与 TaskDock 展开态持久化到 `localStorage`（`workbench.leftWidth` /
  `workbench.rightWidth` / `workbench.taskDockOpen`），拖拽时 clamp 到 min/max。

## 3. ResizablePane（无障碍拖拽）

- Pointer events + setPointerCapture 拖动手柄；
- 键盘：方向键 **8px（单步）/ 24px（大步）**，右栏方向取反；**Home / 双击**复位；
- 手柄 `role="separator" aria-orientation="vertical" aria-valuenow/min/max` +
  `aria-label`（“Prompt 栏宽度” / “参数栏宽度”）。
- 由 `ResizablePane.test.tsx` 覆盖。

## 4. 各区域职责

- **WorkbenchBar**（`WorkbenchBar.tsx`）：模式 segmented、来源上下文（配方 / Prompt /
  当前工作台）、重置工作台、保存为 Prompt/配方（PopoverSelect，含名称、收藏）。
- **Prompt Console**（`PromptConsole.tsx` + `PromptSlotRow.tsx`）：8 个结构化槽位
  （风格/人脸/服饰/动作/场景/镜头/光线/额外）折叠为 label + chip + 单行摘要，仅激活槽位
  展开编辑；素材槽位带 AssetPicker；Negative/Preview 默认收起。
- **Inspector**（`InspectorPanel.tsx`）：工作流、高清放大 `Switch`（标注“原图全部完成后处理”）、
  比例 ChoiceTile、数量（1-64 + 快捷 1/2/4/6/8）、Seed、高级参数。
- **SplitGenerateAction**（`SplitGenerateAction.tsx`）：主“✦ 生成” +
  “优先生成（插入当前任务之后）”；Gate 与旧 GenerateAction 一致（空 prompt / 引擎离线禁用并给原因）。
- **TaskDock**（`TaskDock.tsx`）：收起态显示状态点、第 N/M、总进度、队列数；
  展开态两列（CompactCurrentJob + QueuePanel）；暂停按钮 tooltip 明确
  “只暂停任务调度，不停止 Python/ComfyUI 引擎”。
- **CanvasStage**（`CanvasStage.tsx`）：自包含拉取家族图片、filmstrip、ActionDock、
  Lightbox、ProgressHUD 挂载点。

## 5. 旧组件处置

- `ResultPane.tsx` 被 `CanvasStage` 取代但保留（`ResultPane.lightbox.test.tsx` 仍测，
  避免删测试风险）；
- `components/GenerationControls.tsx` 被 `InspectorPanel` 取代但保留（count 测试仍绿）；
- 已删除：`proto/` 原型、`SettingsPane.compact/queue.test.tsx`（职责已迁移）、
  generate.css 中无 DOM 匹配的 `.generate__columns` / `.generate__modebar` / 1319px 死 CSS。

## 6. 验证

- 布局：`workbenchLayout.test.ts`、`ResizablePane.test.tsx`、
  `GenerateCompactDesktop.test.ts`（三档断点）、`GenerateNoDocumentScroll.test.ts`（零滚动）、
  `GenerateLayoutVisualContract.test.tsx`。
- 浏览器：Dark 1024/1100/1280/1366/1440/1920、窄屏 900（Prompt/配置 Tab）、Light 1024/1280/1440
  均截图确认（见 `UI_VISUAL_ACCEPTANCE.md`）。
