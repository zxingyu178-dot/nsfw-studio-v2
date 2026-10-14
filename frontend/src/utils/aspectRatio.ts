// 画幅 / 分辨率预设（Commit 6）：纯前端便捷选择。
// Job 仍只提交 width/height；画幅与档位选择是组件临时状态，不进入快照 / Recipe / 后端 schema。

/** 预设画幅 key（custom = 用户手填宽高）。 */
export type AspectKey =
  | '1:1'
  | '3:4'
  | '4:5'
  | '9:16'
  | '16:9'
  | '5:4'
  | '4:3'
  | 'custom'

/** 分辨率档位：用“长边像素”驱动。 */
export type ResolutionTier = 'standard' | 'hd'

/** 各档位的长边像素（px）。 */
export const RESOLUTION_LONG_EDGE: Record<ResolutionTier, number> = {
  standard: 1024,
  hd: 1920,
}

/** 像素数超过该阈值时提示“生成较慢”（仅提示，不阻断）。 */
export const SLOW_PIXEL_THRESHOLD = 1_600_000

export const MIN_DIMENSION = 64
export const MAX_DIMENSION = 4096

export type PresetAspectKey = Exclude<AspectKey, 'custom'>

interface RatioDef {
  key: PresetAspectKey
  /** 宽：高 的比（aw : ah），如 9:16 → aw=9, ah=16（竖版）。 */
  aw: number
  ah: number
  label: string
}

/** 预设画幅表（顺序即 UI 展示顺序）。 */
export const ASPECT_RATIOS: RatioDef[] = [
  { key: '1:1', aw: 1, ah: 1, label: '1:1 方形' },
  { key: '3:4', aw: 3, ah: 4, label: '3:4 竖版' },
  { key: '4:5', aw: 4, ah: 5, label: '4:5 竖版' },
  { key: '9:16', aw: 9, ah: 16, label: '9:16 竖版' },
  { key: '16:9', aw: 16, ah: 9, label: '16:9 横版' },
  { key: '5:4', aw: 5, ah: 4, label: '5:4 横版' },
  { key: '4:3', aw: 4, ah: 3, label: '4:3 横版' },
]

/** 对齐到 8 的倍数（出图尺寸友好）。 */
export function snap8(value: number): number {
  return Math.round(value / 8) * 8
}

/** 把任意数值收敛到合法边长区间 [64, 4096]；NaN 回落 1024。 */
export function clampDimension(value: number, min: number = MIN_DIMENSION, max: number = MAX_DIMENSION): number {
  if (Number.isNaN(value)) return 1024
  return Math.min(max, Math.max(min, Math.round(value)))
}

/**
 * 按预设画幅 + 档位计算宽高：
 * - 横版/方形：width=长边，height=对齐8(长边*ah/aw)；
 * - 竖版：height=长边，width=对齐8(长边*aw/ah)；
 * - 1:1：两边=长边。
 */
export function computeDimensions(
  aspect: PresetAspectKey,
  tier: ResolutionTier,
): { width: number; height: number } {
  const def = ASPECT_RATIOS.find((ratio) => ratio.key === aspect)
  if (!def) return { width: 1024, height: 1024 }
  const longEdge = RESOLUTION_LONG_EDGE[tier]
  if (def.aw === def.ah) {
    return { width: longEdge, height: longEdge }
  }
  if (def.aw > def.ah) {
    // 横版
    return { width: longEdge, height: snap8((longEdge * def.ah) / def.aw) }
  }
  // 竖版
  return { width: snap8((longEdge * def.aw) / def.ah), height: longEdge }
}

/**
 * 从已提交的宽高反推最接近的预设画幅；无法匹配则返回 'custom'。
 * 用于从快照 hydrate 后回选对应画幅，避免显示错误。
 */
export function inferAspect(width: number, height: number): AspectKey {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return 'custom'
  }
  const target = width / height
  const TOLERANCE = 0.02
  let best: AspectKey = 'custom'
  let bestDiff = TOLERANCE
  for (const def of ASPECT_RATIOS) {
    const diff = Math.abs(target - def.aw / def.ah)
    if (diff <= bestDiff) {
      best = def.key
      bestDiff = diff
    }
  }
  return best
}

/**
 * 从已提交宽高反推分辨率档位（standard 长边 1024 / hd 长边 1920）。
 * 按“长边”到两档长边的中点（1472）就近归属；不可度量 / 非法尺寸回退 standard。
 * 用于 Recipe / History / 外部 hydrate 后回选档位，避免 UI 高亮与真实提交宽高不一致。
 */
export function deriveTier(width: number, height: number): ResolutionTier {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return 'standard'
  }
  const longEdge = Math.max(width, height)
  const mid = (RESOLUTION_LONG_EDGE.standard + RESOLUTION_LONG_EDGE.hd) / 2
  return longEdge >= mid ? 'hd' : 'standard'
}

/** 总像素是否超过“生成较慢”阈值（仅提示用）。 */
export function isSlowSize(width: number, height: number): boolean {
  return width * height > SLOW_PIXEL_THRESHOLD
}
