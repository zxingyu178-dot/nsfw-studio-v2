import { useId, useState, type ReactNode } from 'react'

export interface TooltipProps {
  content: ReactNode
  children: ReactNode
  side?: 'top' | 'bottom'
  className?: string
}

export function Tooltip({ content, children, side = 'top', className = '' }: TooltipProps) {
  const [open, setOpen] = useState(false)
  const id = useId()
  return (
    <span
      className={`ds-tooltip-wrap ${className}`.trim()}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span aria-describedby={open ? id : undefined} className="ds-tooltip-trigger">
        {children}
      </span>
      {open && (
        <span id={id} role="tooltip" className={`ds-tooltip ds-tooltip--${side}`}>
          {content}
        </span>
      )}
    </span>
  )
}
