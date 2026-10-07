import { useEffect, useState } from 'react'
import { getHealth } from '../api/client'

type Status = 'checking' | 'online' | 'offline'

const STATUS_LABEL: Record<Status, string> = {
  checking: 'Studio 检测中',
  online: 'Studio 在线',
  offline: 'Studio 离线',
}

/**
 * 顶部状态指示（Phase 0.1 语义修正）。
 * 当前检测的是 NSFW Studio 后端 API 健康，因此显示 "Studio 在线/离线"，
 * 不声称引擎连接状态。Phase 1+ 接入 EngineAdapter.health() 后，
 * 本组件将切换为真实引擎状态（显示 "Engine 在线"）。
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
      Studio
    </span>
  )
}
