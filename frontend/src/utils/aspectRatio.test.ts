import { describe, expect, it } from 'vitest'
import {
  ASPECT_RATIOS,
  clampDimension,
  computeDimensions,
  inferAspect,
  isSlowSize,
  snap8,
  type ResolutionTier,
} from './aspectRatio'

describe('computeDimensions 验收红线', () => {
  it('高清档 9:16 = 1080×1920', () => {
    expect(computeDimensions('9:16', 'hd')).toEqual({ width: 1080, height: 1920 })
  })

  it('高清档 16:9 = 1920×1080', () => {
    expect(computeDimensions('16:9', 'hd')).toEqual({ width: 1920, height: 1080 })
  })

  it('标准档 1:1 = 1024×1024', () => {
    expect(computeDimensions('1:1', 'standard')).toEqual({ width: 1024, height: 1024 })
  })

  it('标准档 3:4 = 768×1024', () => {
    expect(computeDimensions('3:4', 'standard')).toEqual({ width: 768, height: 1024 })
  })

  it.each(ASPECT_RATIOS.flatMap((r) => (['standard', 'hd'] as ResolutionTier[]).map((t) => [r.key, t] as const)))(
    '%s %s 的结果两边都是 8 的倍数',
    (key, tier) => {
      const { width, height } = computeDimensions(key, tier)
      expect(width % 8).toBe(0)
      expect(height % 8).toBe(0)
    },
  )

  it('竖版/横版长边等于档位长边', () => {
    expect(computeDimensions('9:16', 'standard').height).toBe(1024)
    expect(computeDimensions('16:9', 'hd').width).toBe(1920)
    expect(computeDimensions('4:5', 'hd').height).toBe(1920)
    expect(computeDimensions('4:3', 'hd').width).toBe(1920)
  })
})

describe('snap8', () => {
  it('对齐到 8 的倍数', () => {
    expect(snap8(1080)).toBe(1080)
    expect(snap8(768)).toBe(768)
    expect(snap8(1083)).toBe(1080)
    expect(snap8(1085)).toBe(1088)
  })
})

describe('clampDimension', () => {
  it('收敛到 64~4096', () => {
    expect(clampDimension(10)).toBe(64)
    expect(clampDimension(99999)).toBe(4096)
    expect(clampDimension(1024)).toBe(1024)
  })
  it('NaN 回落 1024', () => {
    expect(clampDimension(Number.NaN)).toBe(1024)
  })
})

describe('inferAspect', () => {
  it('能回选验收用例对应的画幅', () => {
    expect(inferAspect(1080, 1920)).toBe('9:16')
    expect(inferAspect(1920, 1080)).toBe('16:9')
    expect(inferAspect(1024, 1024)).toBe('1:1')
    expect(inferAspect(768, 1024)).toBe('3:4')
  })

  it('匹配其它预设', () => {
    expect(inferAspect(1024, 1280)).toBe('4:5') // 0.8
    expect(inferAspect(1280, 1024)).toBe('5:4')
    expect(inferAspect(1024, 768)).toBe('4:3')
  })

  it('无法匹配返回 custom', () => {
    expect(inferAspect(1000, 700)).toBe('custom')
    expect(inferAspect(0, 0)).toBe('custom')
  })
})

describe('isSlowSize', () => {
  it('超过 1.6M 命中慢提示', () => {
    expect(isSlowSize(1920, 1080)).toBe(true) // 2.07M
    expect(isSlowSize(1080, 1920)).toBe(true)
    expect(isSlowSize(1024, 1024)).toBe(false)
    expect(isSlowSize(768, 1024)).toBe(false)
  })
})
