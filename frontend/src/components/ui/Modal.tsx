import { useId, useRef, type ReactNode } from 'react'
import { useFocusGuard, useOverlayEsc } from './useOverlay'

export interface ModalProps {
  open: boolean
  onClose: () => void
  title?: ReactNode
  children: ReactNode
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg'
  showClose?: boolean
}

export function Modal({ open, onClose, title, children, footer, size = 'md', showClose = true }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const titleId = useId()
  useFocusGuard(open, panelRef)
  useOverlayEsc(open, onClose)

  if (!open) return null

  return (
    <div className="ds-overlay ds-overlay--center" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div
        ref={panelRef}
        className={`ds-modal ds-modal--${size}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        tabIndex={-1}
      >
        {(title || showClose) && (
          <div className="ds-modal__header">
            {title && (
              <h2 id={titleId} className="ds-modal__title">
                {title}
              </h2>
            )}
            {showClose && (
              <button
                type="button"
                className="ds-modal__close"
                aria-label="关闭"
                onClick={onClose}
              >
                ×
              </button>
            )}
          </div>
        )}
        <div className="ds-modal__body">{children}</div>
        {footer && <div className="ds-modal__footer">{footer}</div>}
      </div>
    </div>
  )
}

/* ===== 确认对话框 ===== */
export interface ConfirmModalProps {
  open: boolean
  title: string
  message: ReactNode
  confirmText?: string
  cancelText?: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmModal({
  open,
  title,
  message,
  confirmText = '确认',
  cancelText = '取消',
  danger,
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      size="sm"
      footer={
        <>
          <button type="button" className="ds-btn ds-btn--secondary ds-btn--md" onClick={onCancel}>
            {cancelText}
          </button>
          <button
            type="button"
            className={`ds-btn ds-btn--${danger ? 'danger' : 'primary'} ds-btn--md`}
            onClick={onConfirm}
            autoFocus
          >
            {confirmText}
          </button>
        </>
      }
    >
      <div className="ds-confirm__message">{message}</div>
    </Modal>
  )
}
