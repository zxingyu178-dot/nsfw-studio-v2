import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

// ===== Mock jobStore 模块：控制队列状态与动作 =====
const mockUseJobStore = vi.fn()
const mockPauseQueue = vi.fn()
const mockResumeQueue = vi.fn()

vi.mock('../../stores/jobStore', () => ({
  useJobStore: (...args: unknown[]) => mockUseJobStore(...args),
  activeJob: vi.fn(() => null),
  cancelJob: vi.fn(),
  pauseJob: vi.fn(),
  pauseQueue: (...args: unknown[]) => mockPauseQueue(...args),
  reorderQueue: vi.fn(),
  resumeJob: vi.fn(),
  resumeQueue: (...args: unknown[]) => mockResumeQueue(...args),
  resumeRemaining: vi.fn(),
  submitGeneration: vi.fn(),
}))

import { SettingsPane } from './SettingsPane'

/** 构造一个带活动队列（有 running job）的 store 状态。 */
function storeWithQueue(queuePaused: boolean) {
  return {
    engine: null,
    engineLoaded: true,
    queue: {
      worker: {
        running: true,
        queue_paused: queuePaused,
        queue_paused_reason: queuePaused ? 'USER_REQUEST' : null,
      },
      // 用最小对象让 queueHasActivity=true；activeJob 已 mock 为 null，不会渲染 CurrentJobCard
      running: { id: 'job_running_1' },
      queued: [],
      paused: [],
    },
    trackedJob: null,
    submitting: false,
    busyJobId: null,
    sseConnected: false,
    lastError: null,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SettingsPane 队列全局暂停 / 继续按钮', () => {
  it('未暂停时显示"暂停队列"按钮，点击触发 pauseQueue', () => {
    mockUseJobStore.mockReturnValue(storeWithQueue(false))
    render(<SettingsPane imageGenAvailable={true} />)

    const btn = screen.getByRole('button', { name: '暂停队列' })
    expect(btn).toBeInTheDocument()
    fireEvent.click(btn)
    expect(mockPauseQueue).toHaveBeenCalledTimes(1)
  })

  it('queue_paused=true 时显示"继续队列"按钮，点击触发 resumeQueue', () => {
    mockUseJobStore.mockReturnValue(storeWithQueue(true))
    render(<SettingsPane imageGenAvailable={true} />)

    const btn = screen.getByRole('button', { name: '继续队列' })
    expect(btn).toBeInTheDocument()
    fireEvent.click(btn)
    expect(mockResumeQueue).toHaveBeenCalledTimes(1)
  })

  it('无活动队列时不显示暂停/继续按钮', () => {
    mockUseJobStore.mockReturnValue({
      engine: null,
      engineLoaded: true,
      queue: {
        worker: { running: false, queue_paused: false },
        running: null,
        queued: [],
        paused: [],
      },
      trackedJob: null,
      submitting: false,
      busyJobId: null,
      sseConnected: false,
      lastError: null,
    })
    render(<SettingsPane imageGenAvailable={true} />)

    expect(screen.queryByRole('button', { name: '暂停队列' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '继续队列' })).not.toBeInTheDocument()
  })
})
