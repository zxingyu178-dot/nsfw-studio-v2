import type { ReactNode } from 'react'

export interface PaneProps {
  title: ReactNode
  actions?: ReactNode
  children: ReactNode
  /** Phase 0.12：固定在卡片底部的操作区（不随 body 滚动），如 Generate 的“生成/优先生成”。 */
  footer?: ReactNode
  className?: string
  bodyClassName?: string
  ariaLabel?: string
}

/** 工作台三栏统一的卡片容器：标题栏 + 可滚动主体 + 可选固定底部操作区。 */
export function Pane({ title, actions, children, footer, className = '', bodyClassName = '', ariaLabel }: PaneProps) {
  return (
    <section className={`wb-pane ${className}`.trim()} aria-label={ariaLabel}>
      <header className="wb-pane__header">
        <h2 className="wb-pane__title">{title}</h2>
        {actions ? <div className="wb-pane__actions">{actions}</div> : null}
      </header>
      <div className={`wb-pane__body ${bodyClassName}`.trim()}>{children}</div>
      {footer ? <footer className="wb-pane__footer">{footer}</footer> : null}
    </section>
  )
}
