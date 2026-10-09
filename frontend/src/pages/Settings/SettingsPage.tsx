import type { Theme } from '../../stores/themeStore'
import { useTheme } from '../../themes/ThemeProvider'
import { RadioGroup } from '../../components/ui'
import './settings.css'

export default function SettingsPage() {
  const { theme, setTheme } = useTheme()

  return (
    <>
      <section className="st-panel">
        <h2 className="st-panel__title">外观</h2>
        <RadioGroup<Theme>
          name="theme"
          value={theme}
          onChange={setTheme}
          direction="column"
          options={[
            { value: 'dark', label: '深色' },
            { value: 'light', label: '浅色' },
          ]}
        />
      </section>

      <section className="st-panel">
        <h2 className="st-panel__title">关于</h2>
        <p className="st-panel__text">
          NSFW Studio V2（v0.8.0）。本地家庭媒体生成与批阅工作台。
        </p>
      </section>
    </>
  )
}
