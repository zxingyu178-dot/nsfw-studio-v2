/**
 * UI3 IconButton —— 统一图标按钮。
 *
 * - 尺寸档 sm/md/lg；状态 active（选中/切换）/ disabled / loading；
 * - 语义 tone：muted（默认）/ active（accent）/ success（绿）/ danger（红）/ favorite（琥珀）；
 * - 内嵌 Tooltip（label 作为 aria-label 与浮层文案）。
 *
 * 颜色一律走 token：--icon-muted / --icon-active / --icon-success / --icon-danger / --icon-favorite。
 */
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Tooltip, type TooltipSide } from './Tooltip'

export type IconButtonTone = 'muted' | 'active' | 'success' | 'danger' | 'favorite'
export type IconButtonSize = 'sm' | 'md' | 'lg'

export interface IconButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  /** icon 节点（来自 ui3/icons）。 */
  icon: ReactNode
  /** 无障碍标签，同时作为 tooltip 默认文案。 */
  label: string
  tone?: IconButtonTone
  size?: IconButtonSize
  /** 选中/切换态（aria-pressed）。 */
  active?: boolean
  loading?: boolean
  /** 覆盖 tooltip 文案（默认 = label）。传 null 关闭 tooltip。 */
  tooltip?: ReactNode
  tooltipSide?: TooltipSide
}

export function IconButton({
  icon,
  label,
  tone = 'muted',
  size = 'md',
  active = false,
  loading = false,
  tooltip,
  tooltipSide = 'top',
  disabled,
  type = 'button',
  className = '',
  ...rest
}: IconButtonProps) {
  const classes = [
    'ui3-icon-btn',
    `ui3-icon-btn--${tone}`,
    `ui3-icon-btn--${size}`,
    active ? 'ui3-icon-btn--active' : '',
    loading ? 'ui3-icon-btn--loading' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  const button = (
    <button
      type={type}
      className={classes}
      aria-label={label}
      aria-pressed={active || undefined}
      aria-busy={loading || undefined}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? (
        <span className="ui3-spinner" aria-hidden="true" />
      ) : (
        <span className="ui3-icon-btn__glyph">{icon}</span>
      )}
    </button>
  )

  // tooltip 显式传 null = 关闭浮层；否则默认用 label。
  if (tooltip === null) return button
  return (
    <Tooltip content={tooltip ?? label} side={tooltipSide}>
      {button}
    </Tooltip>
  )
}
