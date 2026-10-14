# CANVAS_VIEWPORT_REPORT — v0.15.0（Task 5）

## 1. 定位

`components/CanvasViewport/` 从 `pages/Generate/proto/` 的原型**提升为正式组件**，
是 Workbench 4.0 中栏的图片查看器。目标：**图片无需进入 Lightbox，直接在 Canvas 上
滚轮缩放、拖拽平移**，Lightbox 仅 Gallery 保留。

文件：

- `CanvasViewport.tsx`：组件（ResizeObserver、wheel、pointer 交互、rendition 切换）；
- `geometry.ts`：纯函数几何（fit / zoom-to-cursor / pan clamp / scale clamp）；
- `CanvasViewport.css`：舞台样式（恒定深色哑光 `--canvas-stage-bg`，无 backdrop-filter）；
- `CanvasViewport.test.tsx`：jsdom 固定容器尺寸下的几何/交互测试。

## 2. 坐标模型

```
transform = { scale, tx, ty }
screenX = x * scale + tx
screenY = y * scale + ty
```

## 3. 能力（geometry.ts）

| 函数 | 行为 |
|---|---|
| `fitTransform` | 等比缩放到容器内（padding 8%）并居中，scale 钳制 |
| `fullSizeTransform` | 100% 视图（scale=1）居中 |
| `zoomAtCursor` | **以光标为锚点缩放**：缩放前后光标下内容点位置不变 |
| `wheelFactor` | 上滚放大 / 下滚缩小，指数因子（`exp(-deltaY*0.0016)`） |
| `clampPan` | 平移边界：图比容器宽时最多拖到边缘留 `edgeGrab=40px` 可回抓；窄于容器则锁回居中 |
| `clampScale` | scale ∈ [0.05, 8]，非有限值回退最小 |

## 4. 容器与图片测量

- **ResizeObserver** 监听容器尺寸，容器变化时重新 fit，不依赖 window resize；
- 图片自然尺寸在 `onLoad` 后校正（避免占位尺寸导致首帧错误 fit）；
- **rendition 分层**：
  - `thumbnail`：filmstrip / Prompt 库预览；
  - `preview`：Canvas 常规查看（加载快、清晰度够）；
  - `content`：放大到超过阈值时切换高清，避免直接拉大原图。

## 5. 交互与视觉

- 滚轮以**光标位置**为锚点缩放（非以中心）；
- pointer 拖拽平移，受 `clampPan` 约束，图片不会被完全拖出画布；
- 舞台恒定深色哑光（Dark/Light 一致），`background: var(--canvas-stage-bg)`，
  **无 backdrop-filter**（glassPerformanceGuard 强制）。

## 6. 验证

- 单元/组件：`CanvasViewport.test.tsx` 覆盖 fit 居中、缩放钳制、zoom-to-cursor 不变量、
  平移边界、ResizeObserver 重 fit。
- 几何纯函数可在 jsdom 固定容器尺寸下确定性测试，不依赖真实 GPU。
- 真机拖拽/滚轮：ComfyUI offline 无成片，**未做真机截图**（标注为部分验证）；
  交互逻辑由测试确定性覆盖。

## 7. 与 Lightbox 的边界

- Generate 主 Canvas 不再依赖 Lightbox 看细节（缩放/拖拽就地完成）；
- Gallery 大图浏览仍保留 Lightbox（`.result-stage` / ResultPane 的 lightbox 测试保留）。
