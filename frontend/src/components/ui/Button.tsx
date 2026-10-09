import type { ButtonHTMLAttributes, ReactNode } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'xs' | 'sm' | 'md' | 'lg'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
  icon?: ReactNode
  block?: boolean
}

const sizeClass: Record<ButtonSize, string> = {
  xs: 'ds-btn--xs',
  sm: 'ds-btn--sm',
  md: 'ds-btn--md',
  lg: 'ds-btn--lg',
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  icon,
  block,
  disabled,
  children,
  className = '',
  type = 'button',
  ...rest
}: ButtonProps) {
  const classes = [
    'ds-btn',
    `ds-btn--${variant}`,
    sizeClass[size],
    block ? 'ds-btn--block' : '',
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
      {loading && (
        <span className="ds-btn__spinner" aria-hidden="true">
          <span className="ds-spinner ds-spinner--xs" />
        </span>
      )}
      {!loading && icon && <span className="ds-btn__icon">{icon}</span>}
      {children && <span className="ds-btn__label">{children}</span>}
    </button>
  )
}
