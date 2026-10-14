/**
 * Canvas Progress HUD 计算合同（v0.15 Task 9/13）：
 * - 总进度按全部 Stage 工作单元加权，不能用当前 stage 冒充；
 * - Step 仅在真实采样 step/maxStep 有值时显示；upscale 等非采样阶段必须 indeterminate（处理中…），绝不伪造。
 */
import { describe, expect, it } from 'vitest'
import { hudSnapshot, workOverall } from './workbenchProgress'
import type { LiveProgress } from '../../../stores/jobStore'

function makeJob(opts: { stages: unknown[] }) {
  return {
    id: 'job_1',
    requested_count: 8,
    completed_count: 0,
    items: [],
    started_at: '2026-01-01T00:00:00Z',
    stages: opts.stages,
  } as never
}

function basicStage(over: Record<string, unknown> = {}) {
  return {
    id: 'st_basic',
    stage_index: 0,
    module_id: 'basic_generate',
    status: 'RUNNING',
    total_count: 8,
    completed_count: 2,
    items: [
      { job_item_id: 'it_run', status: 'RUNNING', item_index: 2, progress: 0.5 },
    ],
    ...over,
  }
}

describe('workOverall：跨 Stage 工作单元加权', () => {
  it('basic 单阶段：(completed + 当前 item progress) / total', () => {
    const job = makeJob({ stages: [basicStage()] })
    // (2 + 0.5) / 8 = 31.25% → 31%
    expect(workOverall(job, {})).toBe(31)
  })

  it('basic+upscale 双阶段：总进度=(2+0.5+0)/16，不能用当前 stage 冒充整体', () => {
    const upscale = {
      id: 'st_up',
      stage_index: 1,
      module_id: 'upscale',
      status: 'PENDING',
      total_count: 8,
      completed_count: 0,
      items: [],
    }
    const job = makeJob({ stages: [basicStage(), upscale] })
    // 2.5 / 16 = 15.625% → 16%
    expect(workOverall(job, {})).toBe(16)
  })

  it('实时瞬态 progress 覆盖持久 item.progress', () => {
    const job = makeJob({ stages: [basicStage()] })
    const live: Record<string, LiveProgress> = { it_run: { progress: 1, step: 10, maxStep: 20, updatedAt: 1 } }
    // (2 + 1) / 8 = 37.5% → 38%
    expect(workOverall(job, live)).toBe(38)
  })
})

describe('hudSnapshot：Step 仅采样型，upscale 处理中', () => {
  it('basic 采样：有 step/maxStep 时返回真实 Step，不 indeterminate', () => {
    const job = makeJob({ stages: [basicStage()] })
    const live: Record<string, LiveProgress> = { it_run: { progress: 0.5, step: 10, maxStep: 20, updatedAt: 1 } }
    const hud = hudSnapshot(job, live)
    expect(hud.step).toBe(10)
    expect(hud.maxStep).toBe(20)
    expect(hud.indeterminate).toBe(false)
    expect(hud.stageLabel).toBe('基础生成')
    expect(hud.currentItem).toBe(3)
    expect(hud.itemTotal).toBe(8)
    expect(hud.stageIndex).toBe(1)
    expect(hud.stageCount).toBe(1)
  })

  it('upscale 阶段：即使 step=null 也显示“高清放大/处理中”，绝不伪造 Step', () => {
    const basicDone = {
      id: 'st_basic',
      stage_index: 0,
      module_id: 'basic_generate',
      status: 'COMPLETED',
      total_count: 8,
      completed_count: 8,
      items: [],
    }
    const upRunning = {
      id: 'st_up',
      stage_index: 1,
      module_id: 'upscale',
      status: 'RUNNING',
      total_count: 8,
      completed_count: 1,
      items: [{ job_item_id: 'it_up', status: 'RUNNING', item_index: 1, progress: 0.25 }],
    }
    const job = makeJob({ stages: [basicDone, upRunning] })
    // upscale 引擎不给 step（save_image 类）
    const live: Record<string, LiveProgress> = { it_up: { progress: 0.25, step: null, maxStep: null, updatedAt: 1 } }
    const hud = hudSnapshot(job, live)
    expect(hud.stageLabel).toBe('高清放大')
    expect(hud.step).toBeNull()
    expect(hud.maxStep).toBeNull()
    expect(hud.indeterminate).toBe(true)
    // (8 + 1 + 0.25) / 16 = 57.8125% → 58%
    expect(hud.overall).toBe(58)
  })
})
