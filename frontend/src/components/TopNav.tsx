import { NavLink } from 'react-router-dom'
import { ThemeToggle } from '../components/ThemeToggle'
import { PowerControl } from '../components/PowerMenu'
import { StatusPill } from '../components/ui/ui3'
import { useJobStore } from '../stores/jobStore'

const NAV_ITEMS = [
  { to: '/generate', label: '生成' },
  { to: '/gallery', label: '图库' },
  { to: '/prompts', label: '提示词' },
  { to: '/assets', label: '素材' },
  { to: '/settings', label: '设置' },
]

/**
 * TopNav 右侧 ComfyUI 状态胶囊（Task16 §二十三：状态图标 + 短词，不开大按钮框）。
 * 仅作 glance 展示；丰富的启停状态与操作在 Power 打开的统一 Runtime 面板里。
 */
function ComfyStatusPill() {
  const { engine, engineLoaded } = useJobStore()
  const online = engineLoaded && Boolean(engine?.online)
  return (
    <StatusPill tone={online ? 'online' : 'offline'} pulse={!engineLoaded}>
      COMFY {online ? '在线' : '离线'}
    </StatusPill>
  )
}

export function TopNav() {
  return (
    <header className="topnav">
      <div className="topnav__brand">NSFW Studio</div>
      <nav className="topnav__nav">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `topnav__link${isActive ? ' topnav__link--active' : ''}`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="topnav__right">
        <ComfyStatusPill />
        <ThemeToggle />
        <PowerControl />
      </div>
    </header>
  )
}
