/**
 * UI3 StatusPill —— 状态胶囊（状态点 + 短词）。
 *
 * tone 映射到 token：online(绿) / offline(灰) / starting(琥珀) /
 * external(蓝) / conflict(琥珀) / error(红)。
 */
import type { ReactNode } from 'react'

export type StatusTone =
  | 'online'
  | 'offline'
  | 'starting'
  | 'external'
  | 'conflict'
  | 'error'

export interface StatusPillProps {
  tone?: StatusTone
  children: ReactNode
  className?: string
  /** 是否带呼吸动画（启动中等过渡态）。 */
  pulse?: boolean
}

export function StatusPill({
  tone = 'offline',
  children,
  className = '',
  pulse = false,
}: StatusPillProps) {
  const classes = [
    'ui3-pill',
    `ui3-pill--${tone}`,
    pulse ? 'ui3-pill--pulse' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <span className={classes}>
      <span className="ui3-pill__dot" aria-hidden="true" />
      <span className="ui3-pill__text">{children}</span>
    </span>
  )
}
