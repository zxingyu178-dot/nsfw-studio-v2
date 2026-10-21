import { beforeEach, describe, expect, it, vi } from 'vitest'
import { loadWorkbenchParams, saveWorkbenchParams } from './workbenchPrefs'

beforeEach(() => {
  localStorage.clear()
  vi.resetModules()
})

describe('workbenchStore 参数记忆', () => {
  it('setSize / setCount 会写入参数偏好', async () => {
    const store = await import('./workbenchStore')
    store.setSize(1088, 1920)
    store.setCount(4)
    expect(loadWorkbenchParams()).toMatchObject({ width: 1088, height: 1920, count: 4 })
  })

  it('setSeed 固定 Seed 收敛单张并持久化', async () => {
    const store = await import('./workbenchStore')
    store.setCount(4)
    store.setSeed(424242)
    expect(loadWorkbenchParams()).toEqual({
      width: 1024, height: 1024, count: 1, seedMode: 'fixed', seed: 424242,
    })
  })

  it('初始化时读取已保存参数（刷新后不回到默认尺寸）', async () => {
    saveWorkbenchParams({ width: 832, height: 1216, count: 3, seedMode: 'random', seed: null })
    vi.resetModules()
    const store = await import('./workbenchStore')
    const state = store.getWorkbenchState()
    expect(state.width).toBe(832)
    expect(state.height).toBe(1216)
    expect(state.count).toBe(3)
    expect(state.seedMode).toBe('random')
  })
})
