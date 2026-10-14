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
    liveProgressByItem: {},
    submitting: false,
    lastError: null,
    ...overrides,
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
