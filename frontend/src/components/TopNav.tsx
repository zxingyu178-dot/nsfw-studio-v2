import { NavLink } from 'react-router-dom'
import { EngineStatus } from '../components/EngineStatus'
import { ThemeToggle } from '../components/ThemeToggle'

const NAV_ITEMS = [
  { to: '/generate', label: '生成' },
  { to: '/gallery', label: '图库' },
  { to: '/prompts', label: '提示词' },
  { to: '/assets', label: '素材' },
  { to: '/settings', label: '设置' },
]

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
        <EngineStatus />
        <ThemeToggle />
      </div>
    </header>
  )
}
