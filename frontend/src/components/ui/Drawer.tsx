import { useId, useRef, type ReactNode } from 'react'
import { IconX } from './icons'
import { useFocusGuard, useOverlayEsc } from './useOverlay'

export interface DrawerProps {
  open: boolean
  onClose: () => void
  title?: ReactNode
  children: ReactNode
  width?: 'normal' | 'wide'
  footer?: ReactNode
  showClose?: boolean
}

export function Drawer({ open, onClose, title, children, width = 'normal', footer, showClose = true }: DrawerProps) {
  const panelRef = useRef<HTMLElement>(null)
  const titleId = useId()
  useFocusGuard(open, panelRef)
  useOverlayEsc(open, onClose)

  if (!open) return null

  return (
    <div className="ds-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <aside
        ref={panelRef}
        className={`ds-drawer ${width === 'wide' ? 'ds-drawer--wide' : ''}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        tabIndex={-1}
      >
        <div className="ds-drawer__header">
          {title && (
            <h2 id={titleId} className="ds-drawer__title">
              {title}
            </h2>
          )}
          {showClose && (
            <button type="button" className="ds-drawer__close" aria-label="关闭" onClick={onClose}>
              <IconX size={16} />
            </button>
          )}
        </div>
        <div className="ds-drawer__body">{children}</div>
        {footer && <div className="ds-drawer__footer">{footer}</div>}
      </aside>
    </div>
  )
}
