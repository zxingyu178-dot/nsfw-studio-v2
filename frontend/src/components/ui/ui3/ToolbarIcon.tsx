/**
 * UI3 ToolbarIcon —— 工具栏中的图标项（带选中态）。
 *
 * 与 IconButton 的差别：用于常驻工具条，selected 时给明确的选中底色/高亮，
 * 并以 aria-pressed 表达切换。视觉比 ActionDock 更克制。
 */
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Tooltip, type TooltipSide } from './Tooltip'

export interface ToolbarIconProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  icon: ReactNode
  label: string
  selected?: boolean
  disabled?: boolean
  tooltipSide?: TooltipSide
  className?: string
}

export function ToolbarIcon({
  icon,
  label,
  selected = false,
  disabled,
  tooltipSide = 'bottom',
  className = '',
  type = 'button',
  ...rest
}: ToolbarIconProps) {
  const classes = [
    'ui3-toolbar-icon',
    selected ? 'ui3-toolbar-icon--selected' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <Tooltip content={label} side={tooltipSide}>
      <button
        type={type}
        className={classes}
        aria-label={label}
        aria-pressed={selected}
        disabled={disabled}
        {...rest}
      >
        <span className="ui3-toolbar-icon__glyph">{icon}</span>
      </button>
    </Tooltip>
  )
}
