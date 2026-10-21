/**
 * TaskDock（v0.15 Task 12）：队列能力从右栏迁移到底部任务坞。
 * 展开态保留队列全部能力（固定高度内部滚动、拖拽排序、优先/暂停/继续/取消、暂停后续）。
 * 队列 API 与 0.14 完全一致，仅容器从 SettingsPane 改为 TaskDock。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const mockUseJobStore = vi.fn()
const mockPauseQueue = vi.fn()
const mockResumeQueue = vi.fn()
const mockClearStale = vi.fn(() => Promise.resolve(0))

vi.mock('../../../stores/jobStore', () => ({
  useJobStore: (...args: unknown[]) => mockUseJobStore(...args),
  cancelJob: vi.fn(),
  pauseJob: vi.fn(),
  pauseQueue: (...args: unknown[]) => mockPauseQueue(...args),
  reorderQueue: vi.fn(),
  resumeJob: vi.fn(),
  resumeQueue: (...args: unknown[]) => mockResumeQueue(...args),
  resumeRemaining: vi.fn(),
  clearStaleJobs: () => mockClearStale(),
}))

import { TaskDock } from './TaskDock'
import { setDockOpen } from './workbenchLayout'
import { cancelJob } from '../../../stores/jobStore'

function queuedJob(index: number) {
  return {
    id: `job_q_${index}`,
    status: 'QUEUED',
    positive_prompt_snapshot: `prompt ${index}`.repeat(2),
    requested_count: 1,
    module_id: 'basic_generate',
    stages: [],
  }
}

function storeWithQueue(overrides: Record<string, unknown> = {}) {
  const queued = overrides.queued ?? []
  return {
    queue: {
      worker: { running: true, queue_paused: false, queue_paused_reason: null },
      running: { id: 'job_running_1' },
      queued: queued as unknown[],
      paused: [],
    },
    jobs: [],
    liveProgressByStageItem: {},
    submitting: false,
    busyJobId: null,
    busyJobAction: null,
    lastError: null,
    ...overrides,
  }
}

function runningJob(over: Record<string, unknown> = {}) {
  return {
    id: 'job_running_1',
    status: 'RUNNING',
    positive_prompt_snapshot: 'running prompt',
    requested_count: 1,
    module_id: 'basic_generate',
    pause_requested: false,
    cancel_requested: false,
    stages: [],
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  setDockOpen(true)
})

describe('TaskDock 收起态', () => {
  it('常驻显示运行状态、队列数与“暂停后续”图标（tooltip 文案）', () => {
    mockUseJobStore.mockReturnValue(storeWithQueue({ queued: [queuedJob(0), queuedJob(1)] }))
    setDockOpen(false)
    render(<TaskDock />)
    expect(screen.getByText('队列 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '暂停后续任务' })).toBeInTheDocument()
  })

  it('tooltip 明确“只暂停任务调度，不停止 Python/ComfyUI”', async () => {
    mockUseJobStore.mockReturnValue(storeWithQueue())
    setDockOpen(false)
    render(<TaskDock />)
    const trigger = screen.getByRole('button', { name: '暂停后续任务' })
    fireEvent.mouseEnter(trigger)
    expect(await screen.findByText(/只暂停任务调度，不停止 Python/)).toBeInTheDocument()
  })
})

describe('TaskDock 展开态队列（迁移自 SettingsPane）', () => {
  it('未暂停时显示“暂停队列”，点击触发 pauseQueue', () => {
    mockUseJobStore.mockReturnValue(storeWithQueue())
    render(<TaskDock />)
    const btn = screen.getByRole('button', { name: '暂停队列' })
    fireEvent.click(btn)
    expect(mockPauseQueue).toHaveBeenCalledTimes(1)
  })

  it('queue_paused=true 时显示“继续队列”，点击触发 resumeQueue', () => {
    mockUseJobStore.mockReturnValue(
      storeWithQueue({
        queue: {
          worker: { running: true, queue_paused: true, queue_paused_reason: 'USER_REQUEST' },
          running: { id: 'job_running_1' },
          queued: [],
          paused: [],
        },
      }),
    )
    render(<TaskDock />)
    const btn = screen.getByRole('button', { name: '继续队列' })
    fireEvent.click(btn)
    expect(mockResumeQueue).toHaveBeenCalledTimes(1)
  })

  it('≥20 个排队任务：列表固定 max-height 内部滚动，行可拖拽含优先/暂停/取消', () => {
    mockUseJobStore.mockReturnValue(storeWithQueue({ queued: Array.from({ length: 22 }, (_, i) => queuedJob(i)) }))
    const { container } = render(<TaskDock />)
    const list = container.querySelector('.wb-queue-list') as HTMLElement
    expect(list.style.maxHeight).toBe('300px')
    expect(list.style.overflowY).toBe('auto')
    expect(container.querySelectorAll('.wb-queue-list li[draggable="true"]').length).toBe(22)
    expect(screen.getAllByRole('button', { name: '优先' }).length).toBe(21)
    expect(screen.getAllByRole('button', { name: '暂停' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: '取消' }).length).toBeGreaterThan(0)
  })
})

describe('TaskDock 当前任务动作忙态（v0.15.1 busyJobId 绑定）', () => {
  it('busyJobId 命中当前 running job 且动作为 cancel：取消按钮显示“正在取消…”且动作按钮禁用', () => {
    mockUseJobStore.mockReturnValue(
      storeWithQueue({
        queue: {
          worker: { running: true, queue_paused: false, queue_paused_reason: null },
          running: runningJob(),
          queued: [],
          paused: [],
        },
        busyJobId: 'job_running_1',
        busyJobAction: 'cancel',
      }),
    )
    render(<TaskDock />)
    const cancelBtn = screen.getByRole('button', { name: '正在取消…' })
    expect(cancelBtn).toBeDisabled()
    expect(cancelBtn.getAttribute('aria-busy')).toBe('true')
    // 同一任务的其它动作按钮也禁用（避免并发操作）
    expect(screen.getByRole('button', { name: '暂停' })).toBeDisabled()
  })

  it('busyJobId 指向别的任务时，不误禁用当前 running job 的按钮', () => {
    mockUseJobStore.mockReturnValue(
      storeWithQueue({
        queue: {
          worker: { running: true, queue_paused: false, queue_paused_reason: null },
          running: runningJob(),
          queued: [],
          paused: [],
        },
        busyJobId: 'job_other',
        busyJobAction: 'pause',
      }),
    )
    render(<TaskDock />)
    expect(screen.getByRole('button', { name: '暂停' })).not.toBeDisabled()
    expect(screen.getByRole('button', { name: '取消' })).not.toBeDisabled()
  })
})

describe('TaskDock Phase 0.17.1：收起态常驻阶段与真实 Step', () => {
  function multiStageRunningJob() {
    return runningJob({
      requested_count: 2,
      stages: [
        {
          id: 'stg_1',
          job_id: 'job_running_1',
          stage_index: 0,
          module_id: 'basic_generate',
          status: 'RUNNING',
          total_count: 2,
          completed_count: 0,
          current_item: 0,
          items: [
            { id: 'itm_1', stage_id: 'stg_1', item_index: 0, status: 'RUNNING', progress: 0.5 },
          ],
        },
        {
          id: 'stg_2',
          job_id: 'job_running_1',
          stage_index: 1,
          module_id: 'upscale',
          status: 'QUEUED',
          total_count: 2,
          completed_count: 0,
          items: [],
        },
      ],
    })
  }

  it('收起态显示“阶段 x/y”与“Step x/y”', () => {
    mockUseJobStore.mockReturnValue(
      storeWithQueue({
        queue: {
          worker: { running: true, queue_paused: false, queue_paused_reason: null },
          running: multiStageRunningJob(),
          queued: [],
          paused: [],
        },
        liveProgressByStageItem: { itm_1: { progress: 0.5, step: 12, maxStep: 25 } },
      }),
    )
    setDockOpen(false)
    render(<TaskDock />)
    const dock = screen.getByTestId('task-dock')
    expect(dock.textContent).toContain('阶段 1/2')
    expect(dock.textContent).toContain('Step 12/25')
  })

  it('非采样阶段（如 upscale）不伪造 Step', () => {
    mockUseJobStore.mockReturnValue(
      storeWithQueue({
        queue: {
          worker: { running: true, queue_paused: false, queue_paused_reason: null },
          running: multiStageRunningJob(),
          queued: [],
          paused: [],
        },
        liveProgressByStageItem: { itm_1: { progress: 0.3 } },
      }),
    )
    setDockOpen(false)
    render(<TaskDock />)
    const dock = screen.getByTestId('task-dock')
    expect(dock.textContent).not.toContain('Step')
  })
})

describe('TaskDock 收起态：运行中快捷取消 + 进度条', () => {
  it('运行中显示“取消当前任务”按钮，点击调用 cancelJob', () => {
    mockUseJobStore.mockReturnValue(
      storeWithQueue({
        queue: {
          worker: { running: true, queue_paused: false, queue_paused_reason: null },
          running: runningJob(),
          queued: [],
          paused: [],
        },
      }),
    )
    setDockOpen(false)
    render(<TaskDock />)
    const button = screen.getByRole('button', { name: '取消当前任务' })
    fireEvent.click(button)
    expect(cancelJob).toHaveBeenCalledWith('job_running_1')
  })

  it('运行中显示整体进度条，空闲时不显示', () => {
    mockUseJobStore.mockReturnValue(
      storeWithQueue({
        queue: {
          worker: { running: true, queue_paused: false, queue_paused_reason: null },
          running: runningJob(),
          queued: [],
          paused: [],
        },
      }),
    )
    setDockOpen(false)
    const { unmount } = render(<TaskDock />)
    expect(screen.getByTestId('dock-progress')).toBeInTheDocument()

    unmount()
    mockUseJobStore.mockReturnValue(
      storeWithQueue({
        queue: {
          worker: { running: true, queue_paused: false, queue_paused_reason: null },
          running: null,
          queued: [],
          paused: [],
        },
      }),
    )
    render(<TaskDock />)
    expect(screen.queryByTestId('dock-progress')).toBeNull()
  })

  it('取消请求已发出时取消按钮禁用，避免重复点击', () => {
    mockUseJobStore.mockReturnValue(
      storeWithQueue({
        queue: {
          worker: { running: true, queue_paused: false, queue_paused_reason: null },
          running: runningJob({ cancel_requested: true }),
          queued: [],
          paused: [],
        },
      }),
    )
    setDockOpen(false)
    render(<TaskDock />)
    expect(screen.getByRole('button', { name: '取消当前任务' })).toBeDisabled()
  })
})
