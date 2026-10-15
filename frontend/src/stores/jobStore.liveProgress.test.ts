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
  liveProgressForStageItem,
  refreshJobs,
} from './jobStore'

const EMPTY_QUEUE = { worker: { running: false }, running: null, queued: [], paused: [] }

function progressEvent(over: Partial<JobEventDTO> = {}): JobEventDTO {
  return {
    type: 'ITEM_PROGRESS',
    job_id: 'job_1',
    item_id: 'item_1',
    payload: {
      progress: 0.5, stage: 'sampling', stage_index: 0, step: 17, max_step: 30,
      stage_item_id: 'stage_item_1',
    },
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

describe('jobStore liveProgress（v0.15 Task 8 / v0.15.1 stage_item_id）', () => {
  it('ITEM_PROGRESS 按 stage_item_id 更新瞬态 map（含真实 step/max_step）', () => {
    handleJobEvent(progressEvent())
    const live = getJobStoreState().liveProgressByStageItem['stage_item_1']
    expect(live).toBeDefined()
    expect(live.progress).toBe(0.5)
    expect(live.engineStage).toBe('sampling')
    expect(live.step).toBe(17)
    expect(live.maxStep).toBe(30)
    expect(live.stageItemId).toBe('stage_item_1')
    expect(liveProgressForStageItem(getJobStoreState(), 'stage_item_1')?.step).toBe(17)
  })

  it('同一 job_item_id 的 basic/upscale 两个 stage_item 进度互不覆盖（多阶段隔离）', () => {
    // stage0 基础生成采样中
    handleJobEvent(progressEvent({
      payload: { progress: 0.5, stage: 'sampling', stage_index: 0, step: 15, max_step: 30, stage_item_id: 'stage_item_1' },
    }))
    // 同一 job_item_id（item_1）进入 stage1 放大：必须是另一条 key，不覆盖 stage0
    handleJobEvent(progressEvent({
      payload: { progress: 0.8, stage: 'upscale', stage_index: 1, step: null, max_step: null, stage_item_id: 'stage_item_2' },
    }))
    const map = getJobStoreState().liveProgressByStageItem
    expect(map['stage_item_1'].step).toBe(15)
    expect(map['stage_item_2'].step).toBeNull()
    expect(map['stage_item_2'].engineStage).toBe('upscale')
  })

  it('progress SSE 不每个 tick 触发全量回源（不调 GET /queue、/engine/status）', () => {
    for (let i = 0; i < 10; i++) {
      handleJobEvent(progressEvent({
        payload: { progress: i / 10, stage: 'sampling', stage_index: 0, step: i, max_step: 10, stage_item_id: 'stage_item_1' },
      }))
    }
    vi.advanceTimersByTime(2000)
    expect(mocks.queue).not.toHaveBeenCalled()
    expect(mocks.engineStatus).not.toHaveBeenCalled()
  })

  it('终态事件按 stage_item_id 精确清理；关键 lifecycle 事件才触发回源', async () => {
    handleJobEvent(progressEvent())
    expect(getJobStoreState().liveProgressByStageItem['stage_item_1']).toBeDefined()

    // ITEM_COMPLETED 携带 stage_item_id，只清理该 stage item 的瞬态进度
    handleJobEvent(progressEvent({
      type: 'ITEM_COMPLETED',
      payload: { stage_item_id: 'stage_item_1' },
    }))
    expect(getJobStoreState().liveProgressByStageItem['stage_item_1']).toBeUndefined()

    // 关键 lifecycle 事件（非 progress）触发一次回源
    await vi.runAllTimersAsync()
    expect(mocks.queue).toHaveBeenCalledTimes(1)

    // JOB_COMPLETED 按 job 清理其余瞬态
    handleJobEvent(progressEvent({
      item_id: 'item_2',
      payload: { progress: 0.2, stage: 'sampling', stage_index: 0, stage_item_id: 'stage_item_9' },
    }))
    expect(getJobStoreState().liveProgressByStageItem['stage_item_9']).toBeDefined()
    handleJobEvent({ type: 'JOB_COMPLETED', job_id: 'job_1', time: 't' })
    expect(getJobStoreState().liveProgressByStageItem['stage_item_9']).toBeUndefined()
  })

  it('回源 prune：多阶段同一 job_item_id，stage0 终态不误删 stage1 RUNNING 的进度', async () => {
    // 两条瞬态进度（同一 job_item_id=item_1，分属两个 stage_item）
    handleJobEvent(progressEvent({
      payload: { progress: 1, stage: 'save_image', stage_index: 0, step: null, max_step: null, stage_item_id: 'stage_item_1' },
    }))
    handleJobEvent(progressEvent({
      payload: { progress: 0.8, stage: 'upscale', stage_index: 1, step: null, max_step: null, stage_item_id: 'stage_item_2' },
    }))

    // 后端事实源：stage0 已完成、stage1 仍在运行（共用 job_item_id=item_1）
    const running = {
      id: 'job_1', status: 'RUNNING', requested_count: 1, completed_count: 0,
      stages: [
        {
          id: 's0', stage_index: 0, module_id: 'basic_generate', status: 'COMPLETED',
          total_count: 1, completed_count: 1, current_item: 0,
          items: [{ id: 'stage_item_1', job_item_id: 'item_1', status: 'COMPLETED', progress: 1, item_index: 0 }],
        },
        {
          id: 's1', stage_index: 1, module_id: 'upscale', status: 'RUNNING',
          total_count: 1, completed_count: 0, current_item: 0,
          items: [{ id: 'stage_item_2', job_item_id: 'item_1', status: 'RUNNING', progress: 0.8, item_index: 0 }],
        },
      ],
    }
    mocks.queue.mockResolvedValueOnce({ worker: { running: true }, running, queued: [], paused: [] })
    await refreshJobs()

    const map = getJobStoreState().liveProgressByStageItem
    expect(map['stage_item_1']).toBeUndefined()
    expect(map['stage_item_2']).toBeDefined()
    expect(map['stage_item_2'].engineStage).toBe('upscale')
  })
})
