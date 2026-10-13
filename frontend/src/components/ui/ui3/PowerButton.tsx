/**
 * UI3 PowerButton —— 顶部电源按钮（图标 + 短状态文本，不开大按钮框）。
 *
 * 用于 TopNav 电源区：克制的 icon + 短词，不做大面积 Button 框。
 * status 驱动 icon 颜色（offline / starting / on / error）。
 */
import type { ButtonHTMLAttributes } from 'react'
import { IconPower } from './icons'

export type PowerStatus = 'off' | 'starting' | 'on' | 'error'

export interface PowerButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  status?: PowerStatus
  /** 短状态文本（如 "ENGINE" / "COMFY"）。 */
  label?: string
  /** 状态小词（如 "运行中"）；缺省按 status 推导。 */
  stateText?: string
}

const STATE_TEXT: Record<PowerStatus, string> = {
  off: '未启动',
  starting: '启动中',
  on: '运行中',
  error: '失败',
}

export function PowerButton({
  status = 'off',
  label = '引擎',
  stateText,
  className = '',
  type = 'button',
  ...rest
}: PowerButtonProps) {
  const classes = ['ui3-power', `ui3-power--${status}`, className].filter(Boolean).join(' ')
  return (
    <button type={type} className={classes} {...rest}>
      <span className="ui3-power__icon">
        <IconPower size={16} />
      </span>
      <span className="ui3-power__text">
        <span className="ui3-power__label">{label}</span>
        <span className="ui3-power__state">{stateText ?? STATE_TEXT[status]}</span>
      </span>
    </button>
  )
}
