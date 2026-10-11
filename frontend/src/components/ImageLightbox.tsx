import { useCallback, useEffect, useRef, useState } from 'react'
import { imageContentUrl, type ImageDTO } from '../types/workbench'
import { useFocusGuard } from './ui/useOverlay'
import './ImageLightbox.css'

/**
 * Generate 与 Gallery【共用】的单一全屏看图 Lightbox。
 *
 * - 只渲染当前 index 这一张大图（imageContentUrl），方向键/按钮切换时才加载下一张——
 *   绝不预载整个图库的原图。
 * - 键盘：ESC 关闭；← / → 上一张 / 下一张；+/- 缩放。
 * - 鼠标：滚轮以中心为锚点缩放（clamp 0.25~4）；缩放后按住拖动平移；
 *   点击遮罩空白处关闭、点击图片不关闭。
 * - 默认适应窗口（contain）；切换图片后缩放/平移复位。
 */

export interface ImageLightboxProps {
  images: Array<Pick<ImageDTO, 'id' | 'width' | 'height' | 'kind'>>
  index: number
  onClose: () => void
  onNavigate: (index: number) => void
}

const MIN_SCALE = 0.25
const MAX_SCALE = 4
const ZOOM_STEP = 1.2

const clampScale = (value: number): number =>
  Math.min(MAX_SCALE, Math.max(MIN_SCALE, value))

const ZERO_OFFSET = { x: 0, y: 0 }

export function ImageLightbox({ images, index, onClose, onNavigate }: ImageLightboxProps) {
  // null = 适应窗口（contain）；数字 = 实际缩放倍率
  const [scale, setScale] = useState<number | null>(null)
  const [offset, setOffset] = useState<{ x: number; y: number }>(ZERO_OFFSET)
  const overlayRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ startX: number; startY: number; ox: number; oy: number } | null>(null)

  useFocusGuard(true, overlayRef)

  const clampedIndex = Math.min(Math.max(index, 0), images.length - 1)

  // 切换图片后缩放 / 平移复位
  useEffect(() => {
    setScale(null)
    setOffset(ZERO_OFFSET)
  }, [clampedIndex])

  const zoomBy = useCallback((factor: number) => {
    setScale((current) => clampScale((current ?? 1) * factor))
  }, [])

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
  }, [clampedIndex, images.length, onClose, onNavigate, zoomBy])

  // 打开期间锁定 body 滚动
  useEffect(() => {
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [])

  function resetToFit(): void {
    setScale(null)
    setOffset(ZERO_OFFSET)
  }

  function zoomTo100(): void {
    setScale(1)
    setOffset(ZERO_OFFSET)
  }

  function handleWheel(event: React.WheelEvent): void {
    event.preventDefault()
    zoomBy(event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP)
  }

  function startDrag(event: React.MouseEvent): void {
    // 仅在已放大（非适应窗口）时允许拖动平移
    if (scale === null) return
    event.preventDefault()
    dragRef.current = { startX: event.clientX, startY: event.clientY, ox: offset.x, oy: offset.y }
    const onMove = (moveEvent: MouseEvent): void => {
      const drag = dragRef.current
      if (!drag) return
      setOffset({
        x: drag.ox + moveEvent.clientX - drag.startX,
        y: drag.oy + moveEvent.clientY - drag.startY,
      })
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
  // 仅渲染当前这一张的 content URL；其余图不请求
  const src = imageContentUrl(current.id)
  const transform = scale === null ? undefined : `translate(${offset.x}px, ${offset.y}px) scale(${scale})`

  return (
    <div
      ref={overlayRef}
      className="ds-overlay ds-overlay--center lb-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="图片预览"
      tabIndex={-1}
    >
      <div
        className={`lb-stage${scale === null ? '' : ' lb-stage--zoomed'}`}
        onWheel={handleWheel}
        onMouseDown={(event) => {
          // 点击遮罩空白处（点在 stage 本身而非图片）关闭
          if (event.target === event.currentTarget) onClose()
        }}
      >
        <img
          className="lb-img"
          src={src}
          alt=""
          draggable={false}
          style={scale === null ? undefined : { transform }}
          onMouseDown={startDrag}
        />
      </div>

      <div className="lb-toolbar">
        <span className="lb-count" aria-live="polite">
          {clampedIndex + 1} / {images.length}
        </span>
        <button
          type="button"
          onClick={() => onNavigate(clampedIndex - 1)}
          disabled={clampedIndex <= 0}
        >
          上一张
        </button>
        <button type="button" onClick={resetToFit}>适应窗口</button>
        <button type="button" onClick={zoomTo100}>100%</button>
        <button
          type="button"
          onClick={() => onNavigate(clampedIndex + 1)}
          disabled={clampedIndex >= images.length - 1}
        >
          下一张
        </button>
        <button type="button" onClick={onClose}>关闭</button>
      </div>
    </div>
  )
}

export default ImageLightbox
