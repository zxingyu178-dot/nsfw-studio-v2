import type { PromptEvaluationDimension } from '../../types/workbench'

export const PROMPT_FILTER_PREFS_KEY = 'prompt.filters.v1'

/** 评分下限只提供 3/4/5 三档，避免低价值筛选。 */
export type PromptScoreFloor = '' | '3' | '4' | '5'

const DIMENSIONS: PromptEvaluationDimension[] = [
  'subject', 'clothing', 'scene', 'composition', 'lighting', 'style', 'quality',
]

export interface PromptFilterPrefs {
  q: string
  sort: 'updated_desc' | 'score_desc' | 'score_asc'
  status: '' | 'keep' | 'candidate' | 'eliminated'
  scored: '' | 'true' | 'false'
  /** 以下为 v0.37.6 新增，旧偏好缺失时按“不限”处理。 */
  minScore?: PromptScoreFloor
  dimension?: PromptEvaluationDimension | ''
  minDimension?: PromptScoreFloor
}

function isScoreFloor(value: unknown): value is PromptScoreFloor {
  return value === '' || value === '3' || value === '4' || value === '5'
}

function isDimension(value: unknown): value is PromptEvaluationDimension | '' {
  return value === '' || DIMENSIONS.includes(value as PromptEvaluationDimension)
}

function isPromptFilterPrefs(value: unknown): value is PromptFilterPrefs {
  if (typeof value !== 'object' || value === null) return false
  const prefs = value as Record<string, unknown>
  return (
    typeof prefs.q === 'string' &&
    (prefs.sort === 'updated_desc' || prefs.sort === 'score_desc' || prefs.sort === 'score_asc') &&
    (prefs.status === '' || prefs.status === 'keep' || prefs.status === 'candidate' || prefs.status === 'eliminated') &&
    (prefs.scored === '' || prefs.scored === 'true' || prefs.scored === 'false') &&
    (prefs.minScore === undefined || isScoreFloor(prefs.minScore)) &&
    (prefs.dimension === undefined || isDimension(prefs.dimension)) &&
    (prefs.minDimension === undefined || isScoreFloor(prefs.minDimension))
  )
}

function isDefaultPrefs(prefs: PromptFilterPrefs): boolean {
  return (
    prefs.q === '' &&
    prefs.sort === 'updated_desc' &&
    prefs.status === '' &&
    prefs.scored === '' &&
    (prefs.minScore ?? '') === '' &&
    (prefs.dimension ?? '') === '' &&
    (prefs.minDimension ?? '') === ''
  )
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
