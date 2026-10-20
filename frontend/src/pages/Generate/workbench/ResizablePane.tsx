/**
 * ResizablePane（v0.15 Task 1 §5.2 / Phase 0.17.1）：三栏可拖拽侧栏 + 可收起。
 * - pointer capture 拖拽，不选中文本；clamp min/max；
 * - double click 恢复默认；
 * - 无障碍：role=separator / aria-orientation=vertical / aria-valuenow，
 *   方向键微调（ArrowLeft/Right，Shift 加速），Home 复位；
 * - Phase 0.17.1：collapsed=true 时只渲染 44px 竖栏按钮（点击展开），把宽度让给 Canvas。
 */
import { useRef, type ReactNode } from 'react'
import { IconChevronDown } from '../../../components/ui/ui3'
import { clampWidth } from './workbenchLayout'

export interface ResizablePaneProps {
  side: 'left' | 'right'
  width: number
  min: number
  max: number
  label: string
  onChange: (width: number) => void
  onReset: () => void
  children: ReactNode
  className?: string
  /** Phase 0.17.1：收起态（只留竖栏）。 */
  collapsed?: boolean
  /** 收起/展开按钮的无障碍文案（如「Prompt 栏」「参数栏」）。 */
  collapseLabel?: string
  onToggleCollapse?: () => void
}

const KEY_STEP = 8
const KEY_BIG_STEP = 24

export function ResizablePane({
  side,
  width,
  min,
  max,
  label,
  onChange,
  onReset,
  children,
  className = '',
  collapsed = false,
  collapseLabel = '侧栏',
  onToggleCollapse,
}: ResizablePaneProps) {
  const drag = useRef<{ startX: number; startWidth: number } | null>(null)

  if (collapsed) {
    return (
      <div
        className={`wb4-pane wb4-pane--${side} wb4-pane--collapsed ${className}`.trim()}
        data-width={width}
        data-collapsed="true"
      >
        <button
          type="button"
          className="wb4-pane__rail"
          onClick={onToggleCollapse}
          aria-label={`展开${collapseLabel}`}
          title={`展开${collapseLabel}`}
        >
          <IconChevronDown
            size={14}
            className={`wb4-pane__rail-icon wb4-pane__rail-icon--${side}`}
          />
          <span className="wb4-pane__rail-text">{collapseLabel}</span>
        </button>
      </div>
    )
  }

  function applyDelta(deltaClientX: number): void {
    // 左栏：handle 在右缘，向右拖(deltaX>0)变宽；右栏：handle 在左缘，向左拖(deltaX<0)变宽。
    const delta = side === 'left' ? deltaClientX : -deltaClientX
    onChange(clampWidth(drag.current!.startWidth + delta, min, max))
  }

  function onPointerDown(e: React.PointerEvent<HTMLDivElement>): void {
    drag.current = { startX: e.clientX, startWidth: width }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  function onPointerMove(e: React.PointerEvent<HTMLDivElement>): void {
    if (!drag.current) return
    applyDelta(e.clientX - drag.current.startX)
  }
  function endPointer(e: React.PointerEvent<HTMLDivElement>): void {
    if (e.currentTarget.hasPointerCapture?.(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
    drag.current = null
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>): void {
    const step = e.shiftKey ? KEY_BIG_STEP : KEY_STEP
    // 右栏方向取反：ArrowLeft 对右栏意味着变宽
    const signed = (e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0) * (side === 'left' ? 1 : -1)
    if (signed !== 0) {
      e.preventDefault()
      onChange(clampWidth(width + signed * step, min, max))
    } else if (e.key === 'Home') {
      e.preventDefault()
      onReset()
    }
  }

  return (
    <div
      className={`wb4-pane wb4-pane--${side} ${className}`.trim()}
      data-width={width}
    >
      <div className="wb4-pane__content">{children}</div>
      <div
        className={`wb4-resize-handle wb4-resize-handle--${side}`}
        role="separator"
        aria-orientation="vertical"
        aria-label={label}
        aria-valuenow={width}
        aria-valuemin={min}
        aria-valuemax={max}
        tabIndex={0}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endPointer}
        onPointerCancel={endPointer}
        onDoubleClick={onReset}
        onKeyDown={onKeyDown}
      />
    </div>
  )
}

export default ResizablePane
