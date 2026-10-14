# NSFW Studio v0.14.1 — Workbench 恢复（画幅/分辨率）真机回归报告（WORKBENCH RESTORE TEST）

- 验收日期：2026-10-14（UTC+8）
- 验收对象：日用实例 `projects/nsfw-studio-v2-app`，代码 `6459163`，版本 0.14.1
- 验收方式：本机 Playwright（真实浏览器），**Google Chrome 与 Microsoft Edge 双浏览器**，viewport 1366×860
- 驱动脚本：`temp/workbench_restore_0141.py`
- 证据截图：`temp/wb_restore_recipe.png`、`temp/wb_restore_history.png`、`temp/wb_restore_image.png`、`temp/about_0141.png`

## 目标

验证从三条入口恢复到生成工作台（`/generate`）时，画幅/分辨率（width/height）与来源快照中的真实宽高一致。统一注入契约见 `pages/Generate/workbenchNavigation.ts`；工作台画幅控件 `AspectRatioPicker` 以 `data-testid="size-current"` 文本"当前 W × H"呈现权威宽高。

## 三路径结果（Chrome / Edge 双浏览器一致）

| 路径 | 入口 | 来源快照宽高 | 工作台"当前"显示 | 结果 |
|---|---|---|---|---|
| Recipe | 提示词页 → 配方 → 卡片 → Drawer「在生成工作台打开」 | 1024 × 1024（配方「咖啡店白衬衫」） | 1024 × 1024 | PASS |
| History | 提示词页 → 历史 → 任务卡 → Drawer「在生成工作台打开」 | 832 × 1216（任务 JOB-32d7a79a） | 832 × 1216 | PASS |
| Image | 图库 → 双击图片 Lightbox → 侧栏「重新打开 Workbench」 | 832 × 1216（图片 img_3479793b…） | 832 × 1216 | PASS |

- 每条路径的期望宽高都取自"UI 实际点击的那个来源对象"对应的 API 数据（配方 `current_version.generation_settings`、历史 `root.generation_settings`、图片 `width/height`），保证期望与点击对象一致。
- 恢复后右栏「画面」分组自动回选正确档位：832×1216 为 9:16 / HD 档，自定义宽高框显示 832 与 1216；1024×1024 为 1:1 / 标准档。
- 历史路径同时验证 Prompt 字段、工作流模块（含双指纹）随快照恢复（截图可见结构化 Prompt 各字段已回填）。

## 关于页版本

- 设置页（关于信息）正文含 **0.14.1**，且**不含 0.14.0**（Chrome / Edge 均 PASS）。
- `/api/v1/health` 同步返回 `{"status":"ok","version":"0.14.1"}`。

## 如实记录的边界

- 配方「Phase6 浏览器验收配方」为 img2img + 高清放大工作流（`generation_mode=image`，含输入图），其主模块 `size_mode=input`，工作台「画面」正确显示"跟随输入图（无需设置宽高）"而不渲染宽高框——这是设计语义，不是缺陷；显式宽高断言因此选用纯文本/基础生成配方「咖啡店白衬衫」。
- 验收时 Comfy 已停止（为 Playwright 腾出内存），故截图显示"引擎离线 / 无法提交"；本次仅验证恢复与展示，不要求在恢复后立即提交生成。

## 与自动化测试的关系

- 画幅档位纯函数 `deriveTier`、外部 state 回灌（hydrate）/ 聚焦编辑守卫等已由 vitest 覆盖：`AspectRatioPicker.test.tsx`、`utils/aspectRatio.test.ts`、`workbenchStore.*.test.ts`。
- 本报告补充的是从真实 API 数据出发、经真实 UI 三条入口到工作台的端到端恢复一致性。
