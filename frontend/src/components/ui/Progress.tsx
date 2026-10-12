export interface ProgressBarProps {
  /** 0 ~ 1 */
  value: number
  className?: string
  ariaLabel?: string
  tone?: 'accent' | 'danger' | 'ok'
}

export function ProgressBar({ value, className = '', ariaLabel, tone = 'accent' }: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0))
  return (
    <div
      className={`ds-progress ds-progress--${tone} ${className}`.trim()}
      role="progressbar"
      aria-label={ariaLabel}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped * 100)}
    >
      <span className="ds-progress__fill" style={{ width: `${clamped * 100}%` }} />
    </div>
  )
}

export function Spinner({ size = 'md', className = '', ariaLabel = '加载中' }: { size?: 'xs' | 'sm' | 'md' | 'lg'; className?: string; ariaLabel?: string }) {
  return (
    <span
      role="status"
      aria-label={ariaLabel}
      className={`ds-spinner ds-spinner--${size} ${className}`.trim()}
    />
  )
}
