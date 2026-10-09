import type { ReactNode } from 'react'

export type BadgeTone = 'neutral' | 'accent' | 'ok' | 'warn' | 'danger' | 'info'

export function Badge({
  children,
  tone = 'neutral',
  className = '',
}: {
  children: ReactNode
  tone?: BadgeTone
  className?: string
}) {
  return <span className={`ds-badge ds-badge--${tone} ${className}`.trim()}>{children}</span>
}

/* ===== 状态文字徽标（颜色 + 文字，不只用颜色） ===== */
const statusToneMap: Record<string, BadgeTone> = {
  PENDING: 'neutral',
  QUEUED: 'neutral',
  RUNNING: 'accent',
  PAUSED: 'warn',
  INTERRUPTED: 'warn',
  COMPLETED: 'ok',
  FAILED: 'danger',
  CANCELED: 'neutral',
  CANCELLED: 'neutral',
  KEPT: 'ok',
  REJECTED: 'danger',
  UNREVIEWED: 'neutral',
}

const statusLabelMap: Record<string, string> = {
  PENDING: '等待中',
  QUEUED: '排队中',
  RUNNING: '运行中',
  PAUSED: '已暂停',
  INTERRUPTED: '已中断',
  COMPLETED: '已完成',
  FAILED: '失败',
  CANCELED: '已取消',
  CANCELLED: '已取消',
  KEPT: '已保留',
  REJECTED: '已拒绝',
  UNREVIEWED: '未审阅',
}

export function StatusBadge({ status, className = '' }: { status: string; className?: string }) {
  const tone = statusToneMap[status] ?? 'neutral'
  const label = statusLabelMap[status] ?? status
  return (
    <span className={`ds-badge ds-badge--${tone} ds-status-badge ${className}`.trim()}>
      <span className="ds-status-badge__dot" aria-hidden="true" />
      {label}
    </span>
  )
}
