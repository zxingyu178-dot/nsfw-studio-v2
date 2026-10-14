# NSFW Studio v0.14.1 — Lightbox 滚动隔离修复 真机回归报告（LIGHTBOX SCROLL FIX）

- 验收日期：2026-10-14（UTC+8）
- 验收对象：日用实例 `projects/nsfw-studio-v2-app`，代码 `6459163`，版本 0.14.1
- 验收方式：本机 Playwright（真实浏览器，非 jsdom），**Google Chrome 与 Microsoft Edge 双浏览器**，viewport 1366×860
- 驱动脚本：`temp/lightbox_0141.py`（`PW_CHANNEL=chrome|msedge` 切换）
- 证据截图：`temp/lightbox_0141_open.png`（Lightbox 打开态）、`temp/lightbox_0141_after.png`（关闭后）

## 背景

v0.14.0 真机曾出现：在图库全屏 Lightbox 上滚轮 / 触控板滚动时，背景页面会跟着滚动、关闭后位置丢失。v0.14.1 修复点：

1. 打开 overlay 时同时锁三层滚动容器 `html` / `body` / `.app-shell__main`（应用真正的纵向滚动容器是 `.app-shell__main`，只锁 body 挡不住），并在首次加锁时快照 `main.scrollTop`。
2. `.lb-stage` 的滚轮改用 **native non-passive** `addEventListener('wheel', handler, { passive: false })`，在监听内 `preventDefault()` + `stopPropagation()`；React 的 `onWheel` 是 passive 委托，无法阻止触控板滚动。
3. 嵌套 overlay（Lightbox 内再弹 Confirm）用模块级 ref-count，内层关闭不提前释放外层锁。

## 用例结果（Chrome / Edge 双浏览器一致）

| Case | 内容 | Chrome | Edge |
|---|---|---|---|
| A | 打开后 html/body/main 三层 overflow=hidden，主滚动位置锁定为基线（本次基线 scrollTop=500） | PASS | PASS |
| B | ESC 关闭后三层 overflow 恢复（非 hidden），`.app-shell__main.scrollTop` 精确回到 500 | PASS | PASS |
| C | 在图片上滚轮：图片缩放（`transform … scale(1.2)`），背景 scrollTop 不移动（仍 500） | PASS | PASS |
| D | 在 overlay 背景空白区滚轮：背景 scrollTop 不移动（仍 500） | PASS | PASS |

每浏览器 8 项断言全部通过。

## 方法学要点（避免误判）

- 不能用 Playwright 的 `dblclick()` 打开 Lightbox：其 actionability 会先把卡片 `scrollIntoView`，把主滚动容器拉回顶部，导致"恢复基线"判定失效。脚本改为在 DOM 上对卡片派发原生 `click/click/dblclick`，保持滚动基线不变；基线值在设置后立即读回确认为 500。
- 缩放以滚轮 deltaY 为方向（向上放大、向下缩小），断言以 `.lb-img` 的 `transform` 是否含 `scale(...)` 为准，而非依赖像素级布局。

## 与自动化测试的关系

- 滚动隔离的纯逻辑（含嵌套 overlay Case A/C 联合）已由 vitest 覆盖：`ImageLightbox.nativeWheel.test.tsx`、`ImageLightbox.nestedOverlayLock.test.tsx`、`ImageLightbox.overscroll.test.tsx`、`ImageLightbox.scrollIsolation.test.tsx`、`useOverlayScrollLock.test.ts`。
- 本报告补充的是**真实浏览器**对 native non-passive wheel 与真实滚动容器锁定的端到端验证（jsdom 不做真实布局/滚轮）。

## 触控板（trackpad）说明

触控板两指滚动在 Chromium 中同样走 `wheel` 事件，non-passive 拦截逻辑对其同样生效；本机已做鼠标滚轮真机回归。触控板 pinch 缩放手势属浏览器级页面缩放，本 Lightbox 不接管（与 v0.14.0 一致），不属回归范围。
