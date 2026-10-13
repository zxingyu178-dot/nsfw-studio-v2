/**
 * UI3 ChoiceGrid —— ChoiceTile 容器网格。
 *
 * 默认 auto-fill 自适应列数；可通过 columns 固定列数。
 */
import type { ReactNode } from 'react'

export interface ChoiceGridProps {
  children: ReactNode
  /** 固定列数；缺省自适应。 */
  columns?: number
  className?: string
  label?: string
}

export function ChoiceGrid({ children, columns, className = '', label = '选择网格' }: ChoiceGridProps) {
  const style = columns ? ({ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` } as const) : undefined
  return (
    <div className={`ui3-grid ${className}`.trim()} role="group" aria-label={label} style={style}>
      {children}
    </div>
  )
}
