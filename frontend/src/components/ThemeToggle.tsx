import { useTheme } from '../themes/ThemeProvider'

export function ThemeToggle() {
  const { theme, toggle } = useTheme()
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggle}
      title="切换深色/浅色主题"
      aria-label="切换深色/浅色主题"
    >
      {theme === 'dark' ? '深色' : '浅色'}
    </button>
  )
}
