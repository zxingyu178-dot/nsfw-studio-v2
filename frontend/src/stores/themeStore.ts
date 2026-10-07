// 主题状态（Phase 0 规范 §七）：基于 useSyncExternalStore 的极简 store，
// 持久化到 localStorage，默认深色。
export type Theme = 'dark' | 'light'

const STORAGE_KEY = 'nsfw-studio-theme'

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'dark' || saved === 'light') return saved
  } catch {
    // localStorage 不可用（隐私模式等）时使用默认值
  }
  return 'dark'
}

let currentTheme: Theme = initialTheme()
const listeners = new Set<() => void>()

function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
}

export function getTheme(): Theme {
  return currentTheme
}

export function setTheme(theme: Theme): void {
  currentTheme = theme
  try {
    localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // 持久化失败不影响当前会话
  }
  applyTheme(theme)
  listeners.forEach((listener) => listener())
}

export function toggleTheme(): void {
  setTheme(currentTheme === 'dark' ? 'light' : 'dark')
}

export function subscribeTheme(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

// 模块加载时立即应用一次，避免首帧闪烁
applyTheme(currentTheme)
