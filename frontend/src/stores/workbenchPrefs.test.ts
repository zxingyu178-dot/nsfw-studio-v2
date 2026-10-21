import { beforeEach, describe, expect, it } from 'vitest'
import {
  DEFAULT_WORKBENCH_PARAMS,
  WORKBENCH_PARAMS_KEY,
  loadWorkbenchParams,
  saveWorkbenchParams,
} from './workbenchPrefs'

beforeEach(() => {
  localStorage.clear()
})

describe('workbenchPrefs 参数偏好', () => {
  it('无记录时返回默认参数', () => {
    expect(loadWorkbenchParams()).toEqual(DEFAULT_WORKBENCH_PARAMS)
  })

  it('保存后可原样读回（含固定 Seed）', () => {
    saveWorkbenchParams({ width: 1088, height: 1920, count: 4, seedMode: 'fixed', seed: 123456 })
    expect(loadWorkbenchParams()).toEqual({
      width: 1088,
      height: 1920,
      count: 4,
      seedMode: 'fixed',
      seed: 123456,
    })
  })

  it('损坏 JSON 静默回退默认值', () => {
    localStorage.setItem(WORKBENCH_PARAMS_KEY, '{not-json')
    expect(loadWorkbenchParams()).toEqual(DEFAULT_WORKBENCH_PARAMS)
  })

  it('逐字段校验：非法字段回退默认，合法字段保留', () => {
    localStorage.setItem(WORKBENCH_PARAMS_KEY, JSON.stringify({
      width: 'huge',
      height: 1216,
      count: 999,
      seedMode: 'weird',
      seed: 7,
    }))
    expect(loadWorkbenchParams()).toEqual({
      width: DEFAULT_WORKBENCH_PARAMS.width,
      height: 1216,
      count: DEFAULT_WORKBENCH_PARAMS.count,
      seedMode: 'random',
      seed: null,
    })
  })

  it('固定 Seed 但 seed 非法时回退 null', () => {
    localStorage.setItem(WORKBENCH_PARAMS_KEY, JSON.stringify({
      width: 1024, height: 1024, count: 1, seedMode: 'fixed', seed: 'abc',
    }))
    expect(loadWorkbenchParams()).toMatchObject({ seedMode: 'fixed', seed: null })
  })
})
