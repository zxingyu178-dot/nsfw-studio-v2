import { useEffect, useState } from 'react'
import { getHealth } from '../api/client'
import { useJobStore } from '../stores/jobStore'
import { EngineControlPopover } from './EngineControlPopover'

type Status = 'checking' | 'online' | 'offline'

const STUDIO_LABEL: Record<Status, string> = {
  checking: 'Studio 检测中',
  online: 'Studio 在线',
  offline: 'Studio 离线',
}

/**
 * 顶部状态指示（Phase 2 规范 §五十二；Task4 增加引擎控制 Popover）：
 * - Studio：NSFW Studio 后端 API 健康（/health）；
 * - Engine：真实生成引擎健康（/engine/status）；点击 Engine 指示打开
 *   EngineControlPopover，可在内部启停 / 重启由 Studio 管理的 ComfyUI。
 */
export function EngineStatus() {
  const [studio, setStudio] = useState<Status>('checking')
  const [popoverOpen, setPopoverOpen] = useState(false)
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
      <span className="engine-status-wrap">
        <button
          type="button"
          className={`engine-status engine-status--trigger engine-status--${engineStatus}`}
          aria-label={engineLabel}
          aria-expanded={popoverOpen}
          aria-haspopup="dialog"
          title="生图引擎控制"
          data-engine-trigger="true"
          onClick={() => setPopoverOpen((v) => !v)}
        >
          <span className="engine-status__dot" aria-hidden="true" />
          Engine
        </button>
        {popoverOpen && <EngineControlPopover onClose={() => setPopoverOpen(false)} />}
      </span>
    </span>
  )
}
