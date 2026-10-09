import type { CSSProperties, ReactNode } from 'react'

export interface GridProps {
  children: ReactNode
  /** 最小列宽（px） */
  min?: number
  gap?: 2 | 3 | 4
  className?: string
}

export function Grid({ children, min = 180, gap = 3, className = '' }: GridProps) {
  const style = {
    gridTemplateColumns: `repeat(auto-fill, minmax(${min}px, 1fr))`,
  } as CSSProperties
  return (
    <div className={`ds-grid ds-grid--gap-${gap} ${className}`.trim()} style={style}>
      {children}
    </div>
  )
}
