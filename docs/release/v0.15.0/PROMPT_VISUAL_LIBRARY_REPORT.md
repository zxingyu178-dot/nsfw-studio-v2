# PROMPT_VISUAL_LIBRARY_REPORT — v0.15.0（Task 13/14 可视化 Prompt 库）

## 1. 目标

让 Prompt 库每条记录都有一个**视觉预览区**，一眼看出“这条 Prompt 能产出什么”；
没有产出图时统一显示固定比例、低对比的“暂未生成”，**绝不出现 broken-image**。

## 2. 卡片结构（`PromptTab.tsx`）

```
┌───────────────────────────────────────────┐
│ 名称（★ 收藏标记）            [结构化 tag]   │
│ 摘要（风格/服饰/场景…，≤3 行，单行截断）        │
│ ┌───────────────────────────────────────┐ │
│ │      预览图（文本下方，16:9）           │ │
│ │   有图：lazy thumbnail，点击放大        │ │
│ │   无图：固定 16:9 低对比“暂未生成”       │ │
│ └───────────────────────────────────────┘ │
│ 2026-10-07  [使用][复制][编辑][☆ 收藏]      │
└───────────────────────────────────────────┘
```

顺序：名称/摘要 → **预览（文本下方）** → 时间 → 操作按钮。

## 3. 交互规则

- 预览图用 `imageContentUrl(preview_image_id)` 的 **thumbnail**，`loading="lazy"`；
- **点击预览图**打开 Modal 显示 content 大图；
- 图片 `onError` 自动隐藏，回退占位，不产生裂图图标；
- 无图渲染 `.pp-card__preview--empty`，`aria-label="暂未生成预览"`；
- **整卡不再可点击**（避免误触），操作收敛为 4 个显式按钮：使用 / 复制 / 编辑 / 收藏；
- 收藏调 `promptApi.updateMeta({favorite})` 后 reload 列表；
- “复制”只复制文本，**不打开编辑抽屉**；
- 已归档（archived）记录仍显示预览；
- **不自动覆盖封面**：封面只能在编辑抽屉里显式“设为 Prompt 封面”（明确不做 Prompt 自动换封面）。

## 4. 样式（`prompt.css`）

新增 `.pp-card__preview` / `--empty`、`.pp-card__actions`、`.pp-card__action`、
`.pp-card__preview-modal`；卡片改为 flex column，去除 `cursor:pointer`；
占位固定 16:9 并使用低对比前景，视觉上不与真实图竞争。

## 5. 测试（`PromptTab.cover.test.tsx`，重写为 6 用例）

1. 预览在文本下方，且使用 thumbnail；
2. `preview_image_id=null` → 固定比例“暂未生成”占位；
3. archived 记录仍显示；
4. 点击预览图打开预览 Modal（显示 content url）；
5. 点击“复制”不打开编辑抽屉；
6. 编辑抽屉可显式“设为封面”。

## 6. 验证

- 浏览器截图（当前库内 1 条无图 Prompt）：
  `screenshots/dark_1280x720_prompt_library.png`、
  `screenshots/light_1280x720_prompt_library.png`，均正确显示“暂未生成”。
- “有预览图”真机截图：需真实出图（ComfyUI offline），本次未取得；
  渲染/放大/错误隐藏路径由 6 个单测覆盖（见 `UI_VISUAL_ACCEPTANCE.md` §5）。
