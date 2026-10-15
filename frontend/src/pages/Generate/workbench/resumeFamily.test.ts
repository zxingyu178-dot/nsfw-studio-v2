/**
 * resumeFamily（v0.15.1）合同：
 * - 沿 resume_of_job_id 向上遍历，返回 root→current 完整链；
 * - 单层/无父任务也正确；
 * - 环（cycle）与超深链都安全终止（不死循环、不无限请求）。
 */
import { describe, expect, it, vi } from 'vitest'
import { fetchResumeFamilyJobIds, MAX_RESUME_FAMILY_DEPTH } from './resumeFamily'

function getterOf(map: Record<string, string | null>) {
  const get = vi.fn(async (id: string) => ({ resume_of_job_id: map[id] ?? null }))
  return get
}

describe('fetchResumeFamilyJobIds', () => {
  it('A→B→C 三级链：返回 [A, B, C]（root→current）', async () => {
    const get = getterOf({ A: null, B: 'A', C: 'B' })
    const ids = await fetchResumeFamilyJobIds(get, 'C')
    expect(ids).toEqual(['A', 'B', 'C'])
  })

  it('无父任务（root）：仅返回自身', async () => {
    const get = getterOf({ A: null })
    const ids = await fetchResumeFamilyJobIds(get, 'A')
    expect(ids).toEqual(['A'])
  })

  it('仅一层 parent：返回 [parent, current]', async () => {
    const get = getterOf({ A: null, B: 'A' })
    const ids = await fetchResumeFamilyJobIds(get, 'B')
    expect(ids).toEqual(['A', 'B'])
  })

  it('环保护：A→B→A 形成环时不死循环，按 visited 去重终止', async () => {
    const get = getterOf({ A: 'B', B: 'A' })
    const ids = await fetchResumeFamilyJobIds(get, 'A')
    expect(ids.sort()).toEqual(['A', 'B'])
    expect(get).toHaveBeenCalledTimes(2)
  })

  it('深度上限：超长链最多请求 MAX_RESUME_FAMILY_DEPTH 次', async () => {
    // i 的父是 i-1，构造一条远超上限的链
    const map: Record<string, string | null> = {}
    for (let i = 0; i < 100; i++) map[`j${i}`] = i === 0 ? null : `j${i - 1}`
    const get = getterOf(map)
    const ids = await fetchResumeFamilyJobIds(get, 'j99')
    expect(get).toHaveBeenCalledTimes(MAX_RESUME_FAMILY_DEPTH)
    expect(ids).toHaveLength(MAX_RESUME_FAMILY_DEPTH)
    // 截断后的链最末端是 current（j99）
    expect(ids[ids.length - 1]).toBe('j99')
  })
})
