import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { getHealth } from '../api/client'
import { useJobStore } from '../stores/jobStore'
import { ThemeToggle } from './ThemeToggle'
import { PowerControl } from './PowerMenu'
import { IconGrid, IconImage } from './ui/icons'
import { IconHome, IconQuote, IconSettings, IconSpark, StatusPill } from './ui/ui3'

const NAV_ITEMS = [
  { to: '/', label: '首页', Icon: IconHome },
  { to: '/generate', label: '创作', Icon: IconSpark },
  { to: '/gallery', label: '图库', Icon: IconGrid },
  { to: '/prompts', label: '词库', Icon: IconQuote },
  { to: '/settings', label: '设置', Icon: IconSettings },
  { to: '/assets', label: '素材', Icon: IconImage },
]

export function NavigationRail() {
  const { queue } = useJobStore()
  const activeTasks = queue ? Number(!!queue.running) + queue.queued.length : 0

  return (
    <nav className="nav-rail" aria-label="主导航">
      {NAV_ITEMS.map(({ to, label, Icon }) => (
        <NavLink key={to} to={to} end={to === '/'} className="nav-rail__link">
          <Icon size={18} />
          <span>{label}</span>
          {to === '/generate' && activeTasks > 0 && (
            <span className="nav-rail__count" aria-label={activeTasks + ' 个运行或排队任务'}>
              {activeTasks > 99 ? '99+' : activeTasks}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  )
}

export function TopNav() {
  const { pathname } = useLocation()
  const { engine, engineLoaded } = useJobStore()
  const [studioOnline, setStudioOnline] = useState<boolean | null>(null)
  const page = NAV_ITEMS.find(({ to }) => pathname === to)?.label

  useEffect(() => {
    let active = true
    let checking = false

    const check = async () => {
      if (!active || checking || document.hidden) return
      checking = true
      try {
        const health = await getHealth()
        if (active) setStudioOnline(health.status === 'ok')
      } catch {
        if (active) setStudioOnline(false)
      } finally {
        checking = false
      }
    }

    void check()
    const timer = window.setInterval(check, 15000)
    document.addEventListener('visibilitychange', check)
    return () => {
      active = false
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', check)
    }
  }, [])

  return (
    <header className="topnav">
      {pathname === '/' ? (
        <h1 className="topnav__brand">首页</h1>
      ) : (
        <span className="topnav__brand">{page ?? 'NSFW Studio'}</span>
      )}
      <div className="topnav__right">
        <StatusPill tone={studioOnline ? 'online' : 'offline'} pulse={studioOnline === null}>
          Studio {studioOnline === null ? '检测中' : studioOnline ? '在线' : '离线'}
        </StatusPill>
        <StatusPill tone={engine?.online ? 'online' : 'offline'} pulse={!engineLoaded}>
          ComfyUI {engineLoaded ? (engine?.online ? '在线' : '离线') : '检测中'}
        </StatusPill>
        <ThemeToggle />
        <PowerControl />
      </div>
    </header>
  )
}
