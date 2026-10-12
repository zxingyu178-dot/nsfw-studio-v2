import type { ReactNode } from 'react'

export interface PaneProps {
  title: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
  ariaLabel?: string
}

/** 工作台三栏统一的卡片容器：标题栏 + 可滚动主体。 */
export function Pane({ title, actions, children, className = '', bodyClassName = '', ariaLabel }: PaneProps) {
  return (
    <section className={`wb-pane ${className}`.trim()} aria-label={ariaLabel}>
      <header className="wb-pane__header">
        <h2 className="wb-pane__title">{title}</h2>
        {actions ? <div className="wb-pane__actions">{actions}</div> : null}
      </header>
      <div className={`wb-pane__body ${bodyClassName}`.trim()}>{children}</div>
    </section>
  )
}
