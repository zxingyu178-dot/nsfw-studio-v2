/**
 * UI3 ActionButton —— 次级 / 通用动作按钮（带文字，可选 icon）。
 *
 * 用于参数控制台、队列行、面板内的动作。区别于主生成按钮（GenerateAction 由
 * 消费方基于此扩展）。variant：default（次级）/ danger / primary（弱强调）。
 */
import type { ButtonHTMLAttributes, ReactNode } from 'react'

export type ActionButtonVariant = 'default' | 'danger' | 'primary'

export interface ActionButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  variant?: ActionButtonVariant
  icon?: ReactNode
  loading?: boolean
  /** block 撑满容器宽度。 */
  block?: boolean
  children?: ReactNode
}

export function ActionButton({
  variant = 'default',
  icon,
  loading = false,
  block = false,
  disabled,
  children,
  className = '',
  type = 'button',
  ...rest
}: ActionButtonProps) {
  const classes = [
    'ui3-action-btn',
    `ui3-action-btn--${variant}`,
    block ? 'ui3-action-btn--block' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      type={type}
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && <span className="ui3-spinner" aria-hidden="true" />}
      {!loading && icon && <span className="ui3-action-btn__icon">{icon}</span>}
      {children != null && children !== '' && (
        <span className="ui3-action-btn__label">{children}</span>
      )}
    </button>
  )
}
