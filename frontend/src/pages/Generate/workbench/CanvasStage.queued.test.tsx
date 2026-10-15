/**
 * CanvasStage QUEUED / RUNNING 语义分离（v0.15.1）：
 * - RUNNING 才渲染 ProgressHUD（Step/Stage/Elapsed）与“正在生成”；
 * - QUEUED 不渲染 ProgressHUD，显示“已加入队列 · 前方 N 个任务 · 等待开始”，
 *   并提供“查看当前运行任务”入口切换焦点。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const mockUseJobStore = vi.fn()
const mockTrackJob = vi.fn()

vi.mock('../../../stores/jobStore', () => ({
  useJobStore: () => mockUseJobStore(),
  activeJob: (store: { trackedJob?: unknown; queue?: { running?: unknown } | null }) =>
    store.trackedJob ?? store.queue?.running ?? null,
  trackJob: (...args: unknown[]) => mockTrackJob(...args),
}))

// 重型视觉子组件打桩，聚焦语义分支。
vi.mock('../../../components/CanvasViewport/CanvasViewport', () => ({
  CanvasViewport: () => <div data-testid="canvas-viewport" />,
}))
vi.mock('../../../components/ImageLightbox', () => ({
  ImageLightbox: () => null,
}))

vi.mock('../../../api/client', () => ({
  ApiRequestError: class extends Error {},
  imageApi: {
    list: vi.fn(async () => ({ items: [], total: 0 })),
    favorite: vi.fn(),
    setStatus: vi.fn(),
    get: vi.fn(),
  },
  jobApi: {
    get: vi.fn(async (id: string) => ({ id, resume_of_job_id: null })),
  },
}))

import { CanvasStage } from './CanvasStage'
import type { JobDTO } from '../../../types/workbench'

function job(over: Partial<JobDTO>): JobDTO {
  return {
    id: 'j',
    status: 'RUNNING',
    positive_prompt_snapshot: 'p',
    requested_count: 1,
    completed_count: 0,
    module_id: 'basic_generate',
    pause_requested: false,
    cancel_requested: false,
    stages: [],
    ...over,
  } as unknown as JobDTO
}

function renderStage() {
  return render(
    <MemoryRouter>
      <CanvasStage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CanvasStage RUNNING', () => {
  it('RUNNING 空结果：显示 ProgressHUD 与“正在生成”', async () => {
    const running = job({ id: 'jr1', status: 'RUNNING' })
    mockUseJobStore.mockReturnValue({
      trackedJob: running,
      queue: { running, queued: [], paused: [] },
      liveProgressByStageItem: {},
    })
    renderStage()
    expect(await screen.findByTestId('progress-hud')).toBeInTheDocument()
    expect(screen.getByText('正在生成，完成后逐张显示…')).toBeInTheDocument()
  })
})

describe('CanvasStage QUEUED（v0.15.1）', () => {
  it('QUEUED：不显示 ProgressHUD，显示排队横幅与前方任务数，空结果提示等待开始', async () => {
    const running = job({ id: 'jr1', status: 'RUNNING' })
    const q1 = job({ id: 'jq1', status: 'QUEUED' })
    const tracked = job({ id: 'jq2', status: 'QUEUED' })
    mockUseJobStore.mockReturnValue({
      trackedJob: tracked,
      queue: { running, queued: [q1, tracked], paused: [] },
      liveProgressByStageItem: {},
    })
    const { container } = renderStage()

    // 绝不显示采样 Step HUD
    await waitFor(() => expect(container.querySelector('.result-stage__placeholder')).toBeTruthy())
    expect(screen.queryByTestId('progress-hud')).toBeNull()
    // 排队横幅：前方 1 个任务（jq2 在队列 index 1）
    expect(screen.getByText(/已加入队列 · 前方 1 个任务 · 等待开始/)).toBeInTheDocument()
    // 空结果占位同样表达“排队等待”，而非“正在生成”
    expect(screen.getByText(/已加入队列，前方 1 个任务，等待开始/)).toBeInTheDocument()
    // 可切换到真正运行中的任务
    const switchBtn = screen.getByRole('button', { name: '查看当前运行任务' })
    fireEvent.click(switchBtn)
    expect(mockTrackJob).toHaveBeenCalledWith('jr1')
  })
})
