/**
 * CanvasViewport —— Canvas 视口独立技术验证（§12 proto）。
 *
 * 目的：在 `proto/` 隔离目录里验证「平移 / 以光标为锚缩放 / 适应窗口 / 100% 切换 /
 * 切图重置」这一套视口交互，**不接入任何生产页面**（ResultPane 不 import 本文件）。
 *
 * 设计要点（本轮必须验证的约束）：
 * - 缩放/平移**不得触发页面滚动**：wheel 监听通过 ref + `addEventListener(..., { passive: false })`
 *   绑定，并在 handler 里 `e.preventDefault()`（React 的 onWheel 无法保证 non-passive）。
 * - 与 filmstrip（底部缩略条）wheel 隔离：缩放逻辑只挂在本视口容器上，事件在容器内即被
 *   preventDefault，不冒泡到页面；容器外（filmstrip）的 wheel 不受影响。
 * - 所有几何计算抽成纯函数（下方导出），便于 jsdom 以固定容器尺寸直接单测。
 *
 * 坐标约定：transform 形如 { scale, tx, ty }，内容点 (x,y) 映射到屏幕
 *   screenX = x * scale + tx，screenY = y * scale + ty。
 */
import { useCallback, useEffect, useRef, useState } from 'react'

/** 视口变换（scale：内容→屏幕缩放比；tx/ty：屏幕平移）。 */
export interface ViewTransform {
  scale: number
  tx: number
  ty: number
}

export interface Size {
  width: number
  height: number
}

const DEFAULTS = {
  padding: 0.08,
  minScale: 0.05,
  maxScale: 8,
  zoomPerStep: 0.0016, // 每 wheel step 的灵敏度因子（与 deltaY 相乘后取 exp）
}

/** 把 scale 钳制到 [minScale, maxScale]。 */
export function clampScale(scale: number, min = DEFAULTS.minScale, max = DEFAULTS.maxScale): number {
  if (!Number.isFinite(scale)) return min
  return Math.min(max, Math.max(min, scale))
}

/**
 * 适应窗口：让整张图等比缩放到容器内（留 padding），并居中。
 * 纯函数：给定容器尺寸、图原始尺寸、内边距比例，返回目标 transform。
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
 *   contentUnderCursor = (cursor - translate) / oldScale
 *   newTranslate = cursor - contentUnderCursor * newScale
 */
export function zoomAtCursor(
  current: ViewTransform,
  cursor: { x: number; y: number },
  factor: number,
  min = DEFAULTS.minScale,
  max = DEFAULTS.maxScale,
): ViewTransform {
  const nextScale = clampScale(current.scale * factor, min, max)
  const realFactor = nextScale / current.scale // 钳制后真实生效的比例
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

export interface CanvasViewportProps {
  imageUrl: string
  /** 图片原始像素尺寸（由调用方/onLoad 提供；proto 阶段可直接给）。 */
  imageWidth: number
  imageHeight: number
  /** 初始容器尺寸占位；真实挂载后以 ref 的 getBoundingClientRect 为准。 */
  containerWidth?: number
  containerHeight?: number
}

export function CanvasViewport({
  imageUrl,
  imageWidth,
  imageHeight,
  containerWidth = 800,
  containerHeight = 600,
}: CanvasViewportProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)

  const [transform, setTransform] = useState<ViewTransform>(() =>
    fitTransform(
      { width: containerWidth, height: containerHeight },
      { width: imageWidth, height: imageHeight },
    ),
  )
  // 100% / 适应窗口 切换态
  const [mode, setMode] = useState<'fit' | 'full'>('fit')
  // 拖拽会话
  const drag = useRef<{ startX: number; startY: number; origTx: number; origTy: number } | null>(null)

  /** 读取容器实际尺寸（优先 DOM 布局，回退到 props 占位）。 */
  const containerSize = useCallback((): Size => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (rect && rect.width > 0 && rect.height > 0) {
      return { width: rect.width, height: rect.height }
    }
    return { width: containerWidth, height: containerHeight }
  }, [containerWidth, containerHeight])

  const imageSize = useCallback((): Size => {
    const img = imgRef.current
    if (img && img.naturalWidth > 0) {
      return { width: img.naturalWidth, height: img.naturalHeight }
    }
    return { width: imageWidth, height: imageHeight }
  }, [imageWidth, imageHeight])

  /** 重新适应窗口（reset fit）。 */
  const fitToContainer = useCallback(() => {
    setMode('fit')
    setTransform(fitTransform(containerSize(), imageSize()))
  }, [containerSize, imageSize])

  /** 切图后回到 fit（transform reset 策略：换图即重算适应窗口，避免旧平移残留）。 */
  useEffect(() => {
    fitToContainer()
    // 仅在 imageUrl 变化时重置；尺寸变化不强制重置
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imageUrl])

  /** wheel：non-passive 绑定 + preventDefault，以光标为锚缩放。 */
  useEffect(() => {
    const node = containerRef.current
    if (!node) return
    const onWheel = (e: WheelEvent) => {
      // 关键：阻止页面滚动 / 与 filmstrip 冲突
      e.preventDefault()
      const rect = node.getBoundingClientRect()
      const cursor = { x: e.clientX - rect.left, y: e.clientY - rect.top }
      setTransform((prev) => zoomAtCursor(prev, cursor, wheelFactor(e.deltaY)))
    }
    node.addEventListener('wheel', onWheel, { passive: false })
    return () => node.removeEventListener('wheel', onWheel)
  }, [])

  // ===== pointer 拖拽平移 =====
  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    drag.current = { startX: e.clientX, startY: e.clientY, origTx: transform.tx, origTy: transform.ty }
    if (e.currentTarget.setPointerCapture) e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const session = drag.current
    if (!session) return
    setTransform((prev) => ({
      ...prev,
      tx: session.origTx + (e.clientX - session.startX),
      ty: session.origTy + (e.clientY - session.startY),
    }))
  }
  const endDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    if (
      typeof e.currentTarget.hasPointerCapture === 'function' &&
      e.currentTarget.hasPointerCapture(e.pointerId) &&
      e.currentTarget.releasePointerCapture
    ) {
      e.currentTarget.releasePointerCapture(e.pointerId)
    }
    drag.current = null
  }

  const toggleMode = () => {
    if (mode === 'fit') {
      setMode('full')
      setTransform(fullSizeTransform(containerSize(), imageSize()))
    } else {
      fitToContainer()
    }
  }

  return (
    <div className="canvas-viewport" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="canvas-viewport__toolbar" style={{ display: 'flex', gap: 8, padding: 4 }}>
        <button type="button" className="canvas-viewport__fit" onClick={fitToContainer}>
          适应窗口
        </button>
        <button type="button" className="canvas-viewport__mode" onClick={toggleMode}>
          {mode === 'fit' ? '100%' : '适应'}
        </button>
      </div>
      <div
        ref={containerRef}
        data-testid="canvas-viewport-canvas"
        className="canvas-viewport__stage"
        style={{
          position: 'relative',
          flex: 1,
          overflow: 'hidden',
          touchAction: 'none', // 让指针 drag 在触屏上不被浏览器接管滚动
          background: '#111',
          cursor: drag.current ? 'grabbing' : 'grab',
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <img
          ref={imgRef}
          src={imageUrl}
          alt=""
          draggable={false}
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            width: imageSize().width,
            height: imageSize().height,
            transform: `translate(${transform.tx}px, ${transform.ty}px) scale(${transform.scale})`,
            transformOrigin: '0 0',
            maxWidth: 'none',
          }}
        />
      </div>
    </div>
  )
}

export default CanvasViewport
