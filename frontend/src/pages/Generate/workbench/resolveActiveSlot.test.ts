/**
 * resolveActiveSlot（v0.15.1 active slot localStorage 守卫）：
 * - 合法记忆值（命中 STRUCTURED_FIELDS key）优先；
 * - 非法记忆值（旧值/手工值 "foo"）必须忽略，回退到第一个有内容 slot，否则回退 style；
 * - 绝不返回一个不存在的 slot（避免 8 个 slot 全不 active）。
 */
import { describe, expect, it } from 'vitest'
import { emptyStructured } from '../../../types/workbench'
import { resolveActiveSlot } from './resolveActiveSlot'

describe('resolveActiveSlot', () => {
  it('合法记忆值（如 scene）被采纳', () => {
    expect(resolveActiveSlot(emptyStructured(), 'scene')).toBe('scene')
  })

  it('非法记忆值 "foo" 被忽略，回退到第一个有内容的 slot', () => {
    const s = { ...emptyStructured(), clothing: '白色连衣裙' }
    expect(resolveActiveSlot(s, 'foo')).toBe('clothing')
  })

  it('非法记忆值且全部为空：回退到 style', () => {
    expect(resolveActiveSlot(emptyStructured(), 'foo')).toBe('style')
  })

  it('null 记忆值：回退到第一个有内容的 slot', () => {
    const s = { ...emptyStructured(), face: '短发' }
    expect(resolveActiveSlot(s, null)).toBe('face')
  })

  it('null 记忆值且全部为空：默认 style', () => {
    expect(resolveActiveSlot(emptyStructured(), null)).toBe('style')
  })
})
