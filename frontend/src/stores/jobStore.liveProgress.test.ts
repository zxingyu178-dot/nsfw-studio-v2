import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { JobEventDTO } from '../types/workbench'

// ===== 模拟 api client（不建立真实 EventSource / HTTP） =====
const mocks = vi.hoisted(() => ({
  queue: vi.fn(),
  engineStatus: vi.fn(),
  get: vi.fn(),
}))
vi.mock('../api/client', () => ({
  jobApi: { queue: mocks.queue, engineStatus: mocks.engineStatus, get: mocks.get },
  subscribeJobEvents: vi.fn(() => () => undefined),
  ApiRequestError: class extends Error {},
}))

import {
  __resetJobStoreForTest,
  getJobStoreState,
  handleJobEvent,
  liveProgressForItem,
} from './jobStore'

const EMPTY_QUEUE = { worker: { running: false }, running: null, queued: [], paused: [] }

function progressEvent(over: Partial<JobEventDTO> = {}): JobEventDTO {
  return {
    type: 'ITEM_PROGRESS',
    job_id: 'job_1',
    item_id: 'item_1',
    payload: { progress: 0.5, stage: 'sampling', stage_index: 0, step: 17, max_step: 30 },
    time: '2026-10-14T00:00:00Z',
    ...over,
  }
}

beforeEach(() => {
  vi.useFakeTimers()
  mocks.queue.mockReset().mockResolvedValue(EMPTY_QUEUE)
  mocks.engineStatus.mockReset().mockResolvedValue({ online: false })
  mocks.get.mockReset()
  __resetJobStoreForTest()
})

afterEach(() => {
  vi.useRealTimers()
  __resetJobStoreForTest()
})

describe('jobStore liveProgress（v0.15 Task 8）', () => {
  it('ITEM_PROGRESS 更新 liveProgress 瞬态 map（含真实 step/max_step）', () => {
    handleJobEvent(progressEvent())
    const live = getJobStoreState().liveProgressByItem['item_1']
    expect(live).toBeDefined()
    expect(live.progress).toBe(0.5)
    expect(live.engineStage).toBe('sampling')
    expect(live.step).toBe(17)
    expect(live.maxStep).toBe(30)
    expect(liveProgressForItem(getJobStoreState(), 'item_1')?.step).toBe(17)

    // 非采样阶段（upscale）step 为 null
    handleJobEvent(progressEvent({
      payload: { progress: 0.8, stage: 'upscale', stage_index: 1, step: null, max_step: null },
    }))
    const live2 = getJobStoreState().liveProgressByItem['item_1']
    expect(live2.step).toBeNull()
    expect(live2.maxStep).toBeNull()
    expect(live2.engineStage).toBe('upscale')
  })

  it('progress SSE 不每个 tick 触发全量回源（不调 GET /queue、/engine/status）', () => {
    for (let i = 0; i < 10; i++) {
      handleJobEvent(progressEvent({
        payload: { progress: i / 10, stage: 'sampling', stage_index: 0, step: i, max_step: 10 },
      }))
    }
    vi.advanceTimersByTime(2000)
    expect(mocks.queue).not.toHaveBeenCalled()
    expect(mocks.engineStatus).not.toHaveBeenCalled()
  })

  it('终态事件清理 liveProgress；关键 lifecycle 事件才触发回源', async () => {
    handleJobEvent(progressEvent())
    expect(getJobStoreState().liveProgressByItem['item_1']).toBeDefined()

    // ITEM_COMPLETED 清理该 item 的瞬态进度
    handleJobEvent(progressEvent({ type: 'ITEM_COMPLETED', payload: {} }))
    expect(getJobStoreState().liveProgressByItem['item_1']).toBeUndefined()

    // 关键 lifecycle 事件（非 progress）触发一次回源
    await vi.runAllTimersAsync()
    expect(mocks.queue).toHaveBeenCalledTimes(1)

    // JOB_COMPLETED 按 job 清理其余瞬态
    handleJobEvent(progressEvent({ item_id: 'item_2' }))
    expect(getJobStoreState().liveProgressByItem['item_2']).toBeDefined()
    handleJobEvent({ type: 'JOB_COMPLETED', job_id: 'job_1', time: 't' })
    expect(getJobStoreState().liveProgressByItem['item_2']).toBeUndefined()
  })
})
