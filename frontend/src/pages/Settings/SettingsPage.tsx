import type { Theme } from '../../stores/themeStore'
import { useTheme } from '../../themes/ThemeProvider'

const THEME_OPTIONS: { value: Theme; label: string }[] = [
  { value: 'dark', label: '深色' },
  { value: 'light', label: '浅色' },
]

export default function SettingsPage() {
  const { theme, setTheme } = useTheme()

  return (
    <section className="page">
      <h1 className="page__title">设置</h1>

      <div className="panel">
        <h2 className="panel__title">外观</h2>
        <div className="theme-options">
          {THEME_OPTIONS.map((option) => (
            <label key={option.value} className="theme-option">
              <input
                type="radio"
                name="theme"
                checked={theme === option.value}
                onChange={() => setTheme(option.value)}
              />
              <span>{option.label}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="panel">
        <h2 className="panel__title">关于</h2>
        <p className="panel__text">
          NSFW Studio V2 · Phase 0 工程骨架（v0.1.0）。生成引擎与工作流将在后续阶段接入。
        </p>
      </div>
    </section>
  )
}
