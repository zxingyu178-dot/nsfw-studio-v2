import { useEffect, useState } from 'react'
import { getHealth } from '../api/client'

type Status = 'checking' | 'online' | 'offline'

const STATUS_LABEL: Record<Status, string> = {
  checking: 'Engine 检测中',
  online: 'Engine 在线',
  offline: 'Engine 离线',
}

/**
 * Engine 健康状态指示（Phase 0）。
 * 当前检测的是后端 API 健康；Phase 1+ 将切换为 EngineAdapter.health() 的结果。
 */
export function EngineStatus() {
  const [status, setStatus] = useState<Status>('checking')

  useEffect(() => {
    let cancelled = false

    const check = async () => {
      try {
        const info = await getHealth()
        if (!cancelled) setStatus(info.status === 'ok' ? 'online' : 'offline')
      } catch {
        if (!cancelled) setStatus('offline')
      }
    }

    void check()
    const timer = window.setInterval(check, 15000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  return (
    <span className={`engine-status engine-status--${status}`} aria-label={STATUS_LABEL[status]}>
      <span className="engine-status__dot" aria-hidden="true" />
      Engine
    </span>
  )
}
