/**
 * UI3 Tooltip —— 无障碍轻量 tooltip。
 *
 * 行为：悬停 / 键盘聚焦时显示；通过 aria-describedby 关联；role="tooltip"。
 * 供 IconButton / ToolbarIcon / ActionDock 内所有 icon 按钮复用。
 * content 为空时不包裹、不渲染浮层（透传 children）。
 */
import { useId, useState, type ReactNode } from 'react'

export type TooltipSide = 'top' | 'bottom' | 'left' | 'right'

export interface TooltipProps {
  /** 浮层内容（短文本）。为空则不渲染浮层。 */
  content: ReactNode
  children: ReactNode
  side?: TooltipSide
  className?: string
}

export function Tooltip({ content, children, side = 'top', className = '' }: TooltipProps) {
  const [open, setOpen] = useState(false)
  const id = useId()

  if (content == null || content === '') return <>{children}</>

  return (
    <span
      className={`ui3-tooltip-wrap ${className}`.trim()}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span className="ui3-tooltip-trigger" aria-describedby={open ? id : undefined}>
        {children}
      </span>
      {open && (
        <span role="tooltip" id={id} className={`ui3-tooltip ui3-tooltip--${side}`}>
          {content}
        </span>
      )}
    </span>
  )
}
