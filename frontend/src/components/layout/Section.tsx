import type { ReactNode } from 'react'

/* ===== Section：区块（标题 + 描述 + 主体 + 页脚） ===== */
export interface SectionProps {
  title?: ReactNode
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
  actions?: ReactNode
  className?: string
  bordered?: boolean
}

export function Section({ title, description, children, footer, actions, className = '', bordered = true }: SectionProps) {
  return (
    <section className={`ds-section ${bordered ? 'ds-section--bordered' : ''} ${className}`.trim()}>
      {(title || actions) && (
        <div className="ds-section__header">
          {title && <h2 className="ds-section__title">{title}</h2>}
          {actions && <div className="ds-section__actions">{actions}</div>}
        </div>
      )}
      {description && <p className="ds-section__desc">{description}</p>}
      <div className="ds-section__body">{children}</div>
      {footer && <div className="ds-section__footer">{footer}</div>}
    </section>
  )
}

/* ===== Stack：纵向 / 横向排列（间距 Token） ===== */
export interface StackProps {
  children: ReactNode
  direction?: 'row' | 'column'
  gap?: 1 | 2 | 3 | 4 | 5 | 6 | 8
  align?: 'start' | 'center' | 'end' | 'stretch'
  justify?: 'start' | 'center' | 'end' | 'between'
  wrap?: boolean
  className?: string
}

export function Stack({
  children,
  direction = 'column',
  gap = 3,
  align,
  justify,
  wrap,
  className = '',
}: StackProps) {
  const classes = [
    'ds-stack',
    `ds-stack--${direction}`,
    `ds-stack--gap-${gap}`,
    align ? `ds-stack--align-${align}` : '',
    justify ? `ds-stack--justify-${justify}` : '',
    wrap ? 'ds-stack--wrap' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')
  return <div className={classes}>{children}</div>
}

/* ===== Divider ===== */
export function Divider({ className = '', label }: { className?: string; label?: ReactNode }) {
  if (!label) return <hr className={`ds-divider ${className}`.trim()} />
  return (
    <div className={`ds-divider ds-divider--label ${className}`.trim()}>
      <span>{label}</span>
    </div>
  )
}
