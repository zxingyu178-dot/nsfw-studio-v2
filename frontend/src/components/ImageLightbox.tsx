import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { imageContentUrl, imagePreviewUrl, type ImageDTO } from '../types/workbench'
import { useFocusGuard } from './ui/useOverlay'
import { useOverlayScrollLock } from '../hooks/useOverlayScrollLock'
import {
  ActionDock,
  IconButton,
  IconActualSize,
  IconClose,
  IconFit,
  IconInfo,
  IconNext,
  IconPrev,
} from './ui/ui3'
import './ImageLightbox.css'

/**
 * Generate 与 Gallery【共用】的单一全屏看图 Lightbox。
 *
 * - 只渲染当前 index 这一张，方向键/按钮切换时才加载下一张——绝不预载整个图库。
 * - 渐进加载：初开先载 preview（长边 1536），点「100%」或缩放倍率 ≥1 时才切换 original；
 *   切图后缩放复位 → 回到 preview。快速切图不等待完整原图。
 * - 键盘：ESC 关闭；← / → 上一张 / 下一张；+/- 缩放。
 * - 滚动隔离（Task 9）：打开期间用 useOverlayScrollLock 锁 html/body/.app-shell__main；
 *   .lb-stage 的 wheel 以 native non-passive 监听接管（preventDefault+stopPropagation），
 *   不再用 React onWheel（React 默认 passive，无法拦截触控板滚动）。
 * - 交互（Task 10）：滚轮以鼠标位置为锚点缩放；双击 Fit↔100%；拖动带边界限制；
 *   底部用 UI3 ActionDock + IconButton + SVG icon 浮动坞（不再是文字框按钮）。
 * - 可选 hasMore/onLoadMore：到已加载末尾且还有下一页时，触发加载并 append（全历史导航闭环）。
 *   不传这两个 props 的调用方（Generate/ResultPane 有限列表）维持原边界禁用行为。
 */

export interface ImageLightboxProps {
  images: Array<Pick<ImageDTO, 'id' | 'width' | 'height' | 'kind'>>
  index: number
  onClose: () => void
  onNavigate: (index: number) => void
  // Gallery 传入的图片运行时即完整 ImageDTO；renderSidePanel 收到完整对象。
  renderSidePanel?: (image: ImageDTO) => ReactNode
  /** 已加载末尾之后是否还有下一页（分页图库） */
  hasMore?: boolean
  /** 到末尾按下一张时触发加载下一页（append 后父组件更新 images） */
  onLoadMore?: () => void
  /** 后台正在加载下一页（展示加载态） */
  loadingMore?: boolean
}

const MIN_SCALE = 0.25
const MAX_SCALE = 4
const ZOOM_STEP = 1.2

const clampScale = (value: number): number =>
  Math.min(MAX_SCALE, Math.max(MIN_SCALE, value))

const ZERO_OFFSET = { x: 0, y: 0 }

export function ImageLightbox({ images, index, onClose, onNavigate, renderSidePanel, hasMore = false, onLoadMore, loadingMore = false }: ImageLightboxProps) {
  // null = 适应窗口（contain）；数字 = 实际缩放倍率
  const [scale, setScale] = useState<number | null>(null)
  const [offset, setOffset] = useState<{ x: number; y: number }>(ZERO_OFFSET)
  // Phase 0.12：右侧信息栏可折叠——图占满宽；会话内保持 + localStorage 持久化
  const [infoHidden, setInfoHidden] = useState<boolean>(() => {
    try {
      return localStorage.getItem('lightbox.infoHidden') === '1'
    } catch {
      return false
    }
  })
  const overlayRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<HTMLDivElement | null>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)
  // wheel 监听只在挂载时绑定一次（native non-passive），通过 ref 读取最新 scale/offset。
  const scaleRef = useRef<number | null>(null)
  const offsetRef = useRef<{ x: number; y: number }>(ZERO_OFFSET)
  const dragRef = useRef<{ startX: number; startY: number; ox: number; oy: number } | null>(null)

  /**
   * 拖动边界限制：已放大时允许把图片拖到边缘与 stage 对齐，但不允许完全甩出屏幕。
   * 测量不可用（jsdom / 未布局）时原样返回，保证无测量环境下不钳制测试期望的位移。
   */
  const clampOffset = useCallback((ox: number, oy: number, s: number): { x: number; y: number } => {
    const stage = stageRef.current
    const img = imgRef.current
    if (!stage || !img) return { x: ox, y: oy }
    const sw = stage.clientWidth || stage.getBoundingClientRect().width
    const sh = stage.clientHeight || stage.getBoundingClientRect().height
    const renderedW = img.getBoundingClientRect().width
    const renderedH = img.getBoundingClientRect().height
    if (!sw || !sh || !renderedW || !renderedH) return { x: ox, y: oy }
    // 布局（未缩放）图片尺寸 = 当前渲染尺寸 / 倍率
    const iw = renderedW / s
    const ih = renderedH / s
    // 图片比 stage 大时，最多拖到「图片边缘刚好碰到 stage 边缘」
    const maxX = Math.max(0, (sw - iw * s) / 2)
    const maxY = Math.max(0, (sh - ih * s) / 2)
    return {
      x: Math.min(maxX, Math.max(-maxX, ox)),
      y: Math.min(maxY, Math.max(-maxY, oy)),
    }
  }, [])

  const applyScale = useCallback((nextScale: number | null, nextOffset?: { x: number; y: number }) => {
    scaleRef.current = nextScale
    const off = nextOffset ?? ZERO_OFFSET
    offsetRef.current = off
    setScale(nextScale)
    setOffset(off)
  }, [])

  const toggleInfo = useCallback(() => {
    setInfoHidden((prev) => {
      const next = !prev
      try {
        localStorage.setItem('lightbox.infoHidden', next ? '1' : '0')
      } catch {
        // localStorage 不可用（隐私模式）时仅会话内保持
      }
      return next
    })
  }, [])

  useFocusGuard(true, overlayRef)
  // Task 9：锁实际滚动容器（html/body/.app-shell__main），嵌套 overlay 靠 ref-count。
  useOverlayScrollLock(true)

  const clampedIndex = Math.min(Math.max(index, 0), images.length - 1)

  // 切换图片后缩放 / 平移复位
  useEffect(() => {
    applyScale(null, ZERO_OFFSET)
  }, [clampedIndex, applyScale])

  const zoomBy = useCallback((factor: number) => {
    const current = scaleRef.current ?? 1
    applyScale(clampScale(current * factor), offsetRef.current)
  }, [applyScale])

  // 键盘：ESC 关闭 / ←→ 切换 / + - 缩放
  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      } else if (event.key === 'ArrowLeft') {
        if (clampedIndex > 0) {
          event.preventDefault()
          onNavigate(clampedIndex - 1)
        }
      } else if (event.key === 'ArrowRight') {
        if (clampedIndex < images.length - 1) {
          event.preventDefault()
          onNavigate(clampedIndex + 1)
        } else if (hasMore && onLoadMore) {
          event.preventDefault()
          onLoadMore()
        }
      } else if (event.key === '+' || event.key === '=') {
        event.preventDefault()
        zoomBy(ZOOM_STEP)
      } else if (event.key === '-' || event.key === '_') {
        event.preventDefault()
        zoomBy(1 / ZOOM_STEP)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [clampedIndex, images.length, onClose, onNavigate, zoomBy, hasMore, onLoadMore])

  // Task 9：.lb-stage wheel 用 native non-passive 监听接管滚动链。
  // React 的 onWheel 是 passive 委托，无法 preventDefault；这里直接挂 DOM listener。
  useEffect(() => {
    const stage = stageRef.current
    if (!stage) return
    const onWheel = (event: WheelEvent): void => {
      event.preventDefault()
      event.stopPropagation()
      const current = scaleRef.current ?? 1
      const factor = event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP
      const next = clampScale(current * factor)
      // 以鼠标位置为锚点缩放：保持光标下的内容点不动。
      const rect = stage.getBoundingClientRect()
      const cx = event.clientX - rect.left
      const cy = event.clientY - rect.top
      const ratio = next / current
      const rawX = offsetRef.current.x + (1 - ratio) * (cx - rect.width / 2)
      const rawY = offsetRef.current.y + (1 - ratio) * (cy - rect.height / 2)
      applyScale(next, clampOffset(rawX, rawY, next))
    }
    stage.addEventListener('wheel', onWheel, { passive: false })
    return () => stage.removeEventListener('wheel', onWheel)
  }, [applyScale, clampOffset])

  function resetToFit(): void {
    applyScale(null, ZERO_OFFSET)
  }

  function zoomTo100(): void {
    applyScale(1, ZERO_OFFSET)
  }

  /** 双击图片：适应窗口 ↔ 100% 互切。 */
  function handleDoubleClick(): void {
    if (scaleRef.current === null) {
      zoomTo100()
    } else {
      resetToFit()
    }
  }

  function startDrag(event: React.MouseEvent): void {
    // 仅在已放大（非适应窗口）时允许拖动平移
    if (scaleRef.current === null) return
    event.preventDefault()
    dragRef.current = { startX: event.clientX, startY: event.clientY, ox: offsetRef.current.x, oy: offsetRef.current.y }
    const onMove = (moveEvent: MouseEvent): void => {
      const drag = dragRef.current
      if (!drag) return
      const s = scaleRef.current ?? 1
      const next = clampOffset(
        drag.ox + moveEvent.clientX - drag.startX,
        drag.oy + moveEvent.clientY - drag.startY,
        s,
      )
      applyScale(s, next)
    }
    const onUp = (): void => {
      dragRef.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  if (images.length === 0) return null
  const current = images[clampedIndex]
  // 渐进加载：默认 preview（快速切图）；放大到 100% / 倍率≥1 才切换 original。其余图不请求。
  const showOriginal = scale !== null && scale >= 1
  const src = showOriginal ? imageContentUrl(current.id) : imagePreviewUrl(current.id)
  const atEnd = clampedIndex >= images.length - 1
  const nextLabel = atEnd && hasMore ? (loadingMore ? '加载中…' : '加载更多') : '下一张'
  const handleNext = (): void => {
    if (atEnd && hasMore && onLoadMore) onLoadMore()
    else onNavigate(clampedIndex + 1)
  }
  const transform = scale === null ? undefined : `translate(${offset.x}px, ${offset.y}px) scale(${scale})`

  return (
    <div
      ref={overlayRef}
      className={`ds-overlay ds-overlay--center lb-overlay${infoHidden ? ' lb-overlay--no-side' : ''}`}
      role="dialog"
      aria-modal="true"
      aria-label="图片预览"
      tabIndex={-1}
    >
      <div className="lb-body">
        <div
          ref={stageRef}
          className={`lb-stage${scale === null ? '' : ' lb-stage--zoomed'}`}
          onMouseDown={(event) => {
            // 点击遮罩空白处（点在 stage 本身而非图片）关闭
            if (event.target === event.currentTarget) onClose()
          }}
        >
          <img
            ref={imgRef}
            className="lb-img"
            src={src}
            alt=""
            draggable={false}
            style={scale === null ? undefined : { transform }}
            onMouseDown={startDrag}
            onDoubleClick={handleDoubleClick}
          />
        </div>

        {/* Task 10：底部浮动 Icon Dock（UI3 ActionDock + IconButton + SVG icon） */}
        <div className="lb-dock">
          <ActionDock label="图片操作">
            <span className="lb-count" aria-live="polite">
              {clampedIndex + 1} / {images.length}
            </span>
            <IconButton
              icon={<IconPrev size={16} />}
              label="上一张"
              disabled={clampedIndex <= 0}
              onClick={() => onNavigate(clampedIndex - 1)}
            />
            <IconButton
              icon={<IconFit size={16} />}
              label="适应窗口"
              active={scale === null}
              onClick={resetToFit}
            />
            <IconButton
              icon={<IconActualSize size={16} />}
              label="100%"
              active={scale !== null && Math.abs(scale - 1) < 1e-6}
              onClick={zoomTo100}
            />
            {renderSidePanel && (
              <IconButton
                icon={<IconInfo size={16} />}
                label={infoHidden ? '显示信息' : '隐藏信息'}
                active={!infoHidden}
                onClick={toggleInfo}
              />
            )}
            <IconButton
              icon={<IconNext size={16} />}
              label={nextLabel}
              disabled={atEnd && !(hasMore && onLoadMore)}
              onClick={handleNext}
            />
            <IconButton icon={<IconClose size={16} />} label="关闭" tone="danger" onClick={onClose} />
          </ActionDock>
        </div>
      </div>

      {renderSidePanel && !infoHidden && (
        <div className="lb-side-wrap">{renderSidePanel(current as ImageDTO)}</div>
      )}
    </div>
  )
}

export default ImageLightbox
