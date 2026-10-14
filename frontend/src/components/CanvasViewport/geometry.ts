/**
 * CanvasViewport 视口几何（v0.15 Task 5：从 pages/Generate/proto 提升为生产组件）。
 *
 * 坐标约定：transform = { scale, tx, ty }，内容点 (x,y) 映射到屏幕
 *   screenX = x * scale + tx，screenY = y * scale + ty。
 * 纯函数，全部可在 jsdom 固定容器尺寸下单测。
 */
export interface ViewTransform {
  scale: number
  tx: number
  ty: number
}

export interface Size {
  width: number
  height: number
}

export const DEFAULTS = {
  padding: 0.08,
  minScale: 0.05,
  maxScale: 8,
  zoomPerStep: 0.0016,
  /** 平移边界：图片边缘至少保留多少像素可回抓（与 Lightbox 同思想）。 */
  edgeGrab: 40,
}

/** 把 scale 钳制到 [minScale, maxScale]。 */
export function clampScale(scale: number, min = DEFAULTS.minScale, max = DEFAULTS.maxScale): number {
  if (!Number.isFinite(scale)) return min
  return Math.min(max, Math.max(min, scale))
}

/**
 * 适应窗口：让整张图等比缩放到容器内（留 padding），并居中。
 */
export function fitTransform(
  container: Size,
  image: Size,
  padding = DEFAULTS.padding,
  min = DEFAULTS.minScale,
  max = DEFAULTS.maxScale,
): ViewTransform {
  const availW = container.width * (1 - padding * 2)
  const availH = container.height * (1 - padding * 2)
  const scale = clampScale(
    image.width > 0 && image.height > 0 ? Math.min(availW / image.width, availH / image.height) : 1,
    min,
    max,
  )
  return {
    scale,
    tx: (container.width - image.width * scale) / 2,
    ty: (container.height - image.height * scale) / 2,
  }
}

/** 100% 视图：scale=1，图居中（不钳制到 max 之外，但仍走 min）。 */
export function fullSizeTransform(container: Size, image: Size): ViewTransform {
  return {
    scale: 1,
    tx: (container.width - image.width) / 2,
    ty: (container.height - image.height) / 2,
  }
}

/**
 * 以光标为锚点缩放（zoom-to-cursor）。
 * 关键不变量：缩放前后，光标下的内容点保持在光标位置。
 */
export function zoomAtCursor(
  current: ViewTransform,
  cursor: { x: number; y: number },
  factor: number,
  min = DEFAULTS.minScale,
  max = DEFAULTS.maxScale,
): ViewTransform {
  const nextScale = clampScale(current.scale * factor, min, max)
  const realFactor = nextScale / current.scale
  return {
    scale: nextScale,
    tx: cursor.x - (cursor.x - current.tx) * realFactor,
    ty: cursor.y - (cursor.y - current.ty) * realFactor,
  }
}

/** 由 wheel deltaY 计算缩放因子：上滚(deltaY<0)放大、下滚缩小。 */
export function wheelFactor(deltaY: number): number {
  return Math.exp(-deltaY * DEFAULTS.zoomPerStep)
}

/**
 * 平移边界（Task 5 §9.3）：不能把图片完全拖出画布，至少保留 edgeGrab 像素可回抓。
 * 当图片在某个方向上比容器小（fit 留白），禁止该方向无意义平移，保持居中。
 *
 * 图片在屏幕上的轴区间：[tx, tx + image.width*scale]。
 * 约束（图片比容器宽时）：
 *   - 左边界 tx ∈ [container.width - edgeGrab - scaledW, edgeGrab]
 *   - 即最多把图拖到右边只留 edgeGrab，或左边只留 edgeGrab。
 * 图片比容器窄（scaledW <= container.width）：tx 锁回居中。
 */
export function clampPan(
  current: ViewTransform,
  container: Size,
  image: Size,
  edgeGrab = DEFAULTS.edgeGrab,
): ViewTransform {
  const scaledW = image.width * current.scale
  const scaledH = image.height * current.scale

  let tx = current.tx
  let ty = current.ty

  if (scaledW <= container.width) {
    // 窄于容器：水平居中，不允许平移
    tx = (container.width - scaledW) / 2
  } else {
    const minTx = container.width - edgeGrab - scaledW
    const maxTx = edgeGrab
    tx = Math.min(maxTx, Math.max(minTx, tx))
  }

  if (scaledH <= container.height) {
    ty = (container.height - scaledH) / 2
  } else {
    const minTy = container.height - edgeGrab - scaledH
    const maxTy = edgeGrab
    ty = Math.min(maxTy, Math.max(minTy, ty))
  }

  return { scale: current.scale, tx, ty }
}
