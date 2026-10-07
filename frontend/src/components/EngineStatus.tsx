import { useEffect, useState } from 'react'
import { getHealth } from '../api/client'
import { useJobStore } from '../stores/jobStore'

type Status = 'checking' | 'online' | 'offline'

const STUDIO_LABEL: Record<Status, string> = {
  checking: 'Studio 检测中',
  online: 'Studio 在线',
  offline: 'Studio 离线',
}

/**
 * 顶部状态指示（Phase 2 规范 §五十二）：
 * Studio ● 与 Engine ● 是两个独立状态，不用一个圆点混淆。
 * - Studio：NSFW Studio 后端 API 健康（/health）；
 * - Engine：真实生成引擎健康（/engine/status → Adapter.health()，如本机 ComfyUI）。
 */
export function EngineStatus() {
  const [studio, setStudio] = useState<Status>('checking')
  const { engine, engineLoaded } = useJobStore()

  useEffect(() => {
    let cancelled = false

    const check = async () => {
      try {
        const info = await getHealth()
        if (!cancelled) setStudio(info.status === 'ok' ? 'online' : 'offline')
      } catch {
        if (!cancelled) setStudio('offline')
      }
    }

    void check()
    const timer = window.setInterval(check, 15000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  const engineStatus: Status = engineLoaded ? (engine?.online ? 'online' : 'offline') : 'checking'
  const engineLabel =
    engineStatus === 'checking'
      ? 'Engine 检测中'
      : engineStatus === 'online'
        ? `Engine 在线（${engine?.engine_name ?? ''} ${engine?.engine_version ?? ''}）`
        : `Engine 离线${engine?.detail ? `：${engine.detail}` : ''}`

  return (
    <span className="engine-indicators">
      <span className={`engine-status engine-status--${studio}`} aria-label={STUDIO_LABEL[studio]}>
        <span className="engine-status__dot" aria-hidden="true" />
        Studio
      </span>
      <span className={`engine-status engine-status--${engineStatus}`} aria-label={engineLabel} title={engine?.detail}>
        <span className="engine-status__dot" aria-hidden="true" />
        Engine
      </span>
    </span>
  )
}