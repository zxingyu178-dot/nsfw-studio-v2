/**
 * CanvasViewport —— 生产版 Direct Canvas 视口（v0.15 Task 5，由 proto/CanvasViewport 提升）。
 *
 * 在 proto 已验证交互（以光标为锚缩放 / 拖拽平移 / Fit·100% / 切图重置）之上补齐：
 * - ResizeObserver：容器尺寸变化（浏览器缩放、侧栏拖拽、TaskDrawer 开关、断点）时，
 *   Fit 模式自动重新 fit；用户已手动缩放/平移时保持视图中心，不擅自 reset。
 * - 平移边界（clampPan）：不能把图片完全拖出画布，至少留可回抓边缘；fit 留白方向不允许平移。
 * - rendition 分层：Canvas 默认 /preview；scale≥1（或 100%）后再异步加载 /content，
 *   原图加载完成前保持 preview，不闪白；Filmstrip 用 /thumbnail 由调用方负责。
 * - 滚轮以鼠标为中心缩放、拖拽平移、双击 Fit/100%；wheel non-passive + preventDefault，不触发页面滚动。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  clampPan,
  clampScale,
  fitTransform,
  fullSizeTransform,
  wheelFactor,
  zoomAtCursor,
  type Size,
  type ViewTransform,
} from './geometry'
import './CanvasViewport.css'

export interface CanvasViewportProps {
  /** 默认渲染（/preview）的图片地址。 */
  imageUrl: string
  /** 原图（/content）地址：仅 scale≥1 或 100% 后异步加载；不传则始终用 imageUrl。 */
  contentUrl?: string
  /** 图片原始像素尺寸（由调用方/onLoad 提供）；未知时给占位，onLoad 后以 natural 尺寸重算。 */
  imageWidth?: number
  imageHeight?: number
  /** 初始容器尺寸占位；真实挂载后以 ref 的 getBoundingClientRect 为准。 */
  containerWidth?: number
  containerHeight?: number
  alt?: string
  /** 角标（如 HD / 处理图），浮于左上角。 */
  badge?: React.ReactNode
  /** 可选的“全屏查看”动作（Lightbox 已不是主查看路径）。 */
  onFullscreen?: () => void
}

export function CanvasViewport({
  imageUrl,
  contentUrl,
  imageWidth = 1024,
  imageHeight = 1024,
  containerWidth = 800,
  containerHeight = 600,
  alt = '',
  badge,
  onFullscreen,
}: CanvasViewportProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)

  const [transform, setTransform] = useState<ViewTransform>(() =>
    fitTransform(
      { width: containerWidth, height: containerHeight },
      { width: imageWidth, height: imageHeight },
    ),
  )
  const [mode, setMode] = useState<'fit' | 'full'>('fit')
  /** 用户是否已手动缩放/平移（决定容器 resize 时 refit 还是保持中心）。 */
  const manualRef = useRef(false)
  const drag = useRef<{ startX: number; startY: number; origTx: number; origTy: number } | null>(null)
  const [dragging, setDragging] = useState(false)
  /** 原图加载状态：原图未就绪前保持 preview，不闪白。 */
  const [contentLoaded, setContentLoaded] = useState(false)

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

  const fitToContainer = useCallback(() => {
    manualRef.current = false
    setMode('fit')
    setTransform(fitTransform(containerSize(), imageSize()))
  }, [containerSize, imageSize])

  const goFull = useCallback(() => {
    manualRef.current = true
    setMode('full')
    setTransform(fullSizeTransform(containerSize(), imageSize()))
  }, [containerSize, imageSize])

  const toggleMode = useCallback(() => {
    if (mode === 'fit') goFull()
    else fitToContainer()
  }, [mode, goFull, fitToContainer])

  // 切图：重置为 fit（不残留旧平移/缩放），并复位原图加载态。
  useEffect(() => {
    setContentLoaded(false)
    manualRef.current = false
    setMode('fit')
    setTransform(fitTransform(containerSize(), imageSize()))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imageUrl])

  // wheel：non-passive 绑定 + preventDefault，以光标为锚缩放。
  useEffect(() => {
    const node = containerRef.current
    if (!node) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const rect = node.getBoundingClientRect()
      const cursor = { x: e.clientX - rect.left, y: e.clientY - rect.top }
      manualRef.current = true
      setTransform((prev) => {
        const img = imageSize()
        const c = containerSize()
        const next = zoomAtCursor(prev, cursor, wheelFactor(e.deltaY))
        return clampPan(next, c, img)
      })
    }
    node.addEventListener('wheel', onWheel, { passive: false })
    return () => node.removeEventListener('wheel', onWheel)
  }, [containerSize, imageSize])

  // ResizeObserver：Fit 自动 refit；手动视图保持中心（不 reset）。
  const lastSizeRef = useRef<Size>({ width: containerWidth, height: containerHeight })
  useEffect(() => {
    const node = containerRef.current
    if (!node || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      const rect = entry?.contentRect
      const next: Size =
        rect && rect.width > 0 && rect.height > 0
          ? { width: rect.width, height: rect.height }
          : containerSize()
      const prev = lastSizeRef.current
      if (Math.abs(next.width - prev.width) < 1 && Math.abs(next.height - prev.height) < 1) return
      lastSizeRef.current = next
      setTransform((cur) => {
        const img = imageSize()
        if (!manualRef.current) {
          return fitTransform(next, img)
        }
        // 保持视图中心内容点不动
        const center = { x: prev.width / 2, y: prev.height / 2 }
        const newCenter = { x: next.width / 2, y: next.height / 2 }
        const contentX = (center.x - cur.tx) / cur.scale
        const contentY = (center.y - cur.ty) / cur.scale
        return clampPan(
          { scale: cur.scale, tx: newCenter.x - contentX * cur.scale, ty: newCenter.y - contentY * cur.scale },
          next,
          img,
        )
      })
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [containerSize, imageSize])

  // 切到 100%/放大后若掉回 fit 以下，不需要原图；原图仅在 scale≥1 加载。
  const shouldLoadContent = Boolean(contentUrl) && (mode === 'full' || transform.scale >= 1 - 1e-6)

  // ===== pointer 拖拽平移 =====
  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    drag.current = { startX: e.clientX, startY: e.clientY, origTx: transform.tx, origTy: transform.ty }
    if (e.currentTarget.setPointerCapture) e.currentTarget.setPointerCapture(e.pointerId)
    setDragging(true)
  }
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const session = drag.current
    if (!session) return
    manualRef.current = true
    setTransform((prev) => {
      const moved = {
        ...prev,
        tx: session.origTx + (e.clientX - session.startX),
        ty: session.origTy + (e.clientY - session.startY),
      }
      return clampPan(moved, containerSize(), imageSize())
    })
  }
  const endDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    if (
      e.currentTarget.hasPointerCapture &&
      e.currentTarget.hasPointerCapture(e.pointerId) &&
      e.currentTarget.releasePointerCapture
    ) {
      e.currentTarget.releasePointerCapture(e.pointerId)
    }
    drag.current = null
    setDragging(false)
  }

  const imgStyle = (): React.CSSProperties => ({
    position: 'absolute',
    left: 0,
    top: 0,
    width: imageSize().width,
    height: imageSize().height,
    transform: `translate(${transform.tx}px, ${transform.ty}px) scale(${transform.scale})`,
    transformOrigin: '0 0',
    maxWidth: 'none',
  })

  return (
    <div className="canvas-viewport">
      <div className="canvas-viewport__toolbar" role="toolbar" aria-label="画布视图控制">
        <button type="button" className="canvas-viewport__fit" onClick={fitToContainer}>
          适应窗口
        </button>
        <button type="button" className="canvas-viewport__mode" onClick={toggleMode} aria-pressed={mode === 'full'}>
          {mode === 'full' ? '适应' : '100%'}
        </button>
        {onFullscreen && (
          <button type="button" className="canvas-viewport__full" onClick={onFullscreen}>
            全屏查看
          </button>
        )}
      </div>
      <div
        ref={containerRef}
        data-testid="canvas-viewport-canvas"
        className="canvas-viewport__stage"
        style={{ cursor: dragging ? 'grabbing' : 'grab' }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onDoubleClick={toggleMode}
      >
        <img
          ref={imgRef}
          src={imageUrl}
          alt={alt}
          draggable={false}
          className="canvas-viewport__preview"
          style={imgStyle()}
          onLoad={() => {
            // 调用方未给精确尺寸时，以真实 naturalWidth/Height 重新 fit；手动视图不打断。
            if (!manualRef.current) {
              setTransform(fitTransform(containerSize(), imageSize()))
            }
          }}
        />
        {shouldLoadContent && (
          <img
            src={contentUrl}
            alt={alt}
            draggable={false}
            aria-hidden="true"
            className="canvas-viewport__content"
            style={{ ...imgStyle(), opacity: contentLoaded ? 1 : 0 }}
            onLoad={() => setContentLoaded(true)}
            onError={() => setContentLoaded(false)}
          />
        )}
        {badge ? <div className="canvas-viewport__badge">{badge}</div> : null}
      </div>
    </div>
  )
}

export default CanvasViewport
export { clampScale, fitTransform, fullSizeTransform, zoomAtCursor, wheelFactor, clampPan }
