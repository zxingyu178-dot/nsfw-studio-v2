import type { ReactNode } from 'react'

export interface PageContainerProps {
  children: ReactNode
  /** wide：生成 / 图库；normal：提示词 / 设置 */
  width?: 'normal' | 'wide' | 'full'
  /** fill：全屏应用页（生成工作台），填满 main、内部各栏自滚，动作钉在视口内 */
  fill?: boolean
  className?: string
}

export function PageContainer({ children, width = 'normal', fill = false, className = '' }: PageContainerProps) {
  const fillCls = fill ? 'ds-page--fill' : ''
  return (
    <div className={`ds-page ds-page--${width} ${fillCls} ${className}`.trim()}>
      {children}
    </div>
  )
}

export interface PageHeaderProps {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  className?: string
}

export function PageHeader({ title, description, actions, className = '' }: PageHeaderProps) {
  return (
    <header className={`ds-page-header ${className}`.trim()}>
      <div className="ds-page-header__text">
        <h1 className="ds-page-header__title">{title}</h1>
        {description && <p className="ds-page-header__desc">{description}</p>}
      </div>
      {actions && <div className="ds-page-header__actions">{actions}</div>}
    </header>
  )
}
