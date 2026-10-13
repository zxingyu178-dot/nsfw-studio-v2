/**
 * UI3 ActionDock —— 底部浮动图标坞容器。
 *
 * Lightbox 与 Generate 中栏悬浮动作共用：圆角浮层、克制背景、内部水平排列
 * 若干 IconButton / ToolbarIcon。定位由消费方用外层容器控制（absolute/fixed），
 * 本组件只负责外观与排布。
 */
import type { ReactNode } from 'react'

export interface ActionDockProps {
  children: ReactNode
  className?: string
  /** 语义角色，默认 toolbar。 */
  label?: string
}

export function ActionDock({ children, className = '', label = '动作坞' }: ActionDockProps) {
  return (
    <div className={`ui3-dock ${className}`.trim()} role="toolbar" aria-label={label}>
      {children}
    </div>
  )
}
