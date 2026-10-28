import { useState } from 'react'

/**
 * Phase 0.12 Task13：Gallery UI 偏好持久化（仅 localStorage，不入 DB）。
 * - density：网格密度 compact(≈130) / normal(≈180) / large(≈250) minmax
 * - fit：contain(适应，默认，完整构图) / cover(填充，裁切)
 */

export type GalleryDensity = 'compact' | 'normal' | 'large'
export type GalleryFit = 'contain' | 'cover'
/** v0.37 P1-B：整齐网格（默认，统一媒体框）| 瀑布流（按原始比例错列）。 */
export type GalleryLayout = 'grid' | 'waterfall'

export const LAYOUT_OPTIONS: { value: GalleryLayout; label: string }[] = [
  { value: 'grid', label: '整齐网格' },
  { value: 'waterfall', label: '瀑布流' },
]

export const FIT_OPTIONS: { value: GalleryFit; label: string }[] = [
  { value: 'contain', label: '完整显示' },
  { value: 'cover', label: '填充显示' },
]

export const DENSITY_OPTIONS: { value: GalleryDensity; label: string }[] = [
  { value: 'compact', label: '小' },
  { value: 'normal', label: '中' },
  { value: 'large', label: '大' },
]

const DENSITY_KEY = 'gallery.density'
const FIT_KEY = 'gallery.fit'
const LAYOUT_KEY = 'gallery.layout'

function readPref<T>(key: string, fallback: T, valid: readonly T[]): T {
  try {
    const raw = window.localStorage.getItem(key)
    if (raw !== null && (valid as readonly T[]).includes(raw as T)) return raw as T
  } catch {
    // localStorage 不可用（隐私模式 / SSR）时静默回退默认
  }
  return fallback
}

function writePref(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // 忽略写入失败
  }
}

export function useGalleryPrefs() {
  const [density, setDensityState] = useState<GalleryDensity>(() =>
    readPref(DENSITY_KEY, 'normal', ['compact', 'normal', 'large'] as const),
  )
  const [fit, setFitState] = useState<GalleryFit>(() =>
    readPref(FIT_KEY, 'contain', ['contain', 'cover'] as const),
  )
  const [layout, setLayoutState] = useState<GalleryLayout>(() =>
    readPref(LAYOUT_KEY, 'grid', ['grid', 'waterfall'] as const),
  )

  const setDensity = (value: GalleryDensity): void => {
    setDensityState(value)
    writePref(DENSITY_KEY, value)
  }
  const setFit = (value: GalleryFit): void => {
    setFitState(value)
    writePref(FIT_KEY, value)
  }
  const setLayout = (value: GalleryLayout): void => {
    setLayoutState(value)
    writePref(LAYOUT_KEY, value)
  }

  return { density, setDensity, fit, setFit, layout, setLayout }
}
