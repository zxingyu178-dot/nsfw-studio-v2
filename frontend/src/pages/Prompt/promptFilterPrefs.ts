export const PROMPT_FILTER_PREFS_KEY = 'prompt.filters.v1'

export interface PromptFilterPrefs {
  q: string
  sort: 'updated_desc' | 'score_desc' | 'score_asc'
  status: '' | 'keep' | 'candidate' | 'eliminated'
  scored: '' | 'true' | 'false'
}

function isPromptFilterPrefs(value: unknown): value is PromptFilterPrefs {
  if (typeof value !== 'object' || value === null) return false
  const prefs = value as Record<string, unknown>
  return (
    typeof prefs.q === 'string' &&
    (prefs.sort === 'updated_desc' || prefs.sort === 'score_desc' || prefs.sort === 'score_asc') &&
    (prefs.status === '' || prefs.status === 'keep' || prefs.status === 'candidate' || prefs.status === 'eliminated') &&
    (prefs.scored === '' || prefs.scored === 'true' || prefs.scored === 'false')
  )
}

function isDefaultPrefs(prefs: PromptFilterPrefs): boolean {
  return prefs.q === '' && prefs.sort === 'updated_desc' && prefs.status === '' && prefs.scored === ''
}

export function readPromptFilterPrefs(): PromptFilterPrefs | null {
  try {
    const raw = localStorage.getItem(PROMPT_FILTER_PREFS_KEY)
    if (raw === null) return null
    const value: unknown = JSON.parse(raw)
    return isPromptFilterPrefs(value) ? value : null
  } catch {
    return null
  }
}

export function writePromptFilterPrefs(prefs: PromptFilterPrefs): void {
  try {
    if (isDefaultPrefs(prefs)) {
      localStorage.removeItem(PROMPT_FILTER_PREFS_KEY)
      return
    }
    localStorage.setItem(PROMPT_FILTER_PREFS_KEY, JSON.stringify(prefs))
  } catch {
    /* 隐私模式等场景忽略持久化失败 */
  }
}

export function clearPromptFilterPrefs(): void {
  try {
    localStorage.removeItem(PROMPT_FILTER_PREFS_KEY)
  } catch {
    /* 隐私模式等场景忽略清理失败 */
  }
}
