import { describe, expect, it } from 'vitest'
import { formatElapsed } from './elapsed'

describe('formatElapsed', () => {
  it('0 → 00:00', () => {
    expect(formatElapsed(0)).toBe('00:00')
  })
  it('65 → 01:05', () => {
    expect(formatElapsed(65)).toBe('01:05')
  })
  it('3661 → 01:01:01（超过 1 小时用 hh:mm:ss）', () => {
    expect(formatElapsed(3661)).toBe('01:01:01')
  })
  it('不足 1 小时补零到 mm:ss', () => {
    expect(formatElapsed(5)).toBe('00:05')
    expect(formatElapsed(600)).toBe('10:00')
  })
  it('负值 / NaN 按 0 处理', () => {
    expect(formatElapsed(-10)).toBe('00:00')
    expect(formatElapsed(Number.NaN)).toBe('00:00')
  })
})
