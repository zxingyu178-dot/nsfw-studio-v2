import { createContext, useContext, useSyncExternalStore, type ReactNode } from 'react'
import {
  getTheme,
  setTheme as setThemeInStore,
  subscribeTheme,
  toggleTheme,
  type Theme,
} from '../stores/themeStore'

interface ThemeContextValue {
  theme: Theme
  toggle: () => void
  setTheme: (theme: Theme) => void
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'dark',
  toggle: () => undefined,
  setTheme: () => undefined,
})

/** 主题提供者：状态存于 themeStore（localStorage 持久化），此处同步到 <html data-theme>。 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const theme = useSyncExternalStore(subscribeTheme, getTheme)
  return (
    <ThemeContext.Provider value={{ theme, toggle: toggleTheme, setTheme: setThemeInStore }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext)
}
