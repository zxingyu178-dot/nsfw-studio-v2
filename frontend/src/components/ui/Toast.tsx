import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { IconAlert, IconCheck, IconInfo, IconX } from './icons'

export type ToastTone = 'success' | 'error' | 'info'

export interface ToastItem {
  id: number
  tone: ToastTone
  message: ReactNode
  duration: number
}

interface ToastContextValue {
  show: (message: ReactNode, tone?: ToastTone, duration?: number) => void
  success: (message: ReactNode, duration?: number) => void
  error: (message: ReactNode, duration?: number) => void
  info: (message: ReactNode, duration?: number) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

const toneIcon = {
  success: IconCheck,
  error: IconAlert,
  info: IconInfo,
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const counter = useRef(0)
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>())

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.current.delete(id)
    }
  }, [])

  const show = useCallback(
    (message: ReactNode, tone: ToastTone = 'info', duration = 3200) => {
      counter.current += 1
      const id = counter.current
      setToasts((prev) => [...prev.slice(-4), { id, tone, message, duration }])
      if (duration > 0) {
        const timer = setTimeout(() => dismiss(id), duration)
        timers.current.set(id, timer)
      }
    },
    [dismiss]
  )

  const value = useMemo<ToastContextValue>(
    () => ({
      show,
      success: (m, d) => show(m, 'success', d),
      error: (m, d) => show(m, 'error', d ?? 5000),
      info: (m, d) => show(m, 'info', d),
    }),
    [show]
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="ds-toast-container" aria-live="polite" aria-atomic="false">
        {toasts.map((t) => {
          const Icon = toneIcon[t.tone]
          return (
            <div key={t.id} className={`ds-toast ds-toast--${t.tone}`} role="status">
              <span className="ds-toast__icon" aria-hidden="true">
                <Icon size={16} />
              </span>
              <span className="ds-toast__message">{t.message}</span>
              <button type="button" className="ds-toast__close" aria-label="关闭通知" onClick={() => dismiss(t.id)}>
                <IconX size={13} />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast 必须在 ToastProvider 内使用')
  return ctx
}
