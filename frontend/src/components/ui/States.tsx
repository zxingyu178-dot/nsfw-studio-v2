import type { ReactNode } from 'react'
import { IconAlert, IconImage } from './icons'

/* ===== EmptyState ===== */
export interface EmptyStateProps {
  title: string
  description?: ReactNode
  action?: ReactNode
  icon?: ReactNode
  className?: string
  compact?: boolean
}

export function EmptyState({ title, description, action, icon, className = '', compact }: EmptyStateProps) {
  return (
    <div className={`ds-empty ${compact ? 'ds-empty--compact' : ''} ${className}`.trim()}>
      <div className="ds-empty__icon" aria-hidden="true">
        {icon ?? <IconImage size={28} />}
      </div>
      <h3 className="ds-empty__title">{title}</h3>
      {description && <p className="ds-empty__desc">{description}</p>}
      {action && <div className="ds-empty__action">{action}</div>}
    </div>
  )
}

/* ===== ErrorState ===== */
export interface ErrorStateProps {
  title?: string
  error?: ReactNode
  onRetry?: () => void
  retryText?: string
  className?: string
}

export function ErrorState({ title = '加载失败', error, onRetry, retryText = '重试', className = '' }: ErrorStateProps) {
  return (
    <div className={`ds-error-state ${className}`.trim()} role="alert">
      <div className="ds-error-state__icon" aria-hidden="true">
        <IconAlert size={26} />
      </div>
      <h3 className="ds-error-state__title">{title}</h3>
      {error && <p className="ds-error-state__detail">{error}</p>}
      {onRetry && (
        <button type="button" className="ds-btn ds-btn--secondary ds-btn--sm" onClick={onRetry}>
          {retryText}
        </button>
      )}
    </div>
  )
}

/* ===== Skeleton ===== */
export function Skeleton({ className = '', width, height }: { className?: string; width?: number | string; height?: number | string }) {
  return (
    <span
      className={`ds-skeleton ${className}`.trim()}
      style={{ width, height }}
      aria-hidden="true"
    />
  )
}

/** 与卡片网格同构的骨架占位 */
export function CardGridSkeleton({ count = 8, cardClass = '' }: { count?: number; cardClass?: string }) {
  return (
    <div className="ds-skeleton-grid" aria-busy="true" aria-label="加载中">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className={`ds-skeleton-card ${cardClass}`.trim()}>
          <Skeleton className="ds-skeleton-card__media" />
          <Skeleton width="70%" height={12} />
          <Skeleton width="40%" height={10} />
        </div>
      ))}
    </div>
  )
}
