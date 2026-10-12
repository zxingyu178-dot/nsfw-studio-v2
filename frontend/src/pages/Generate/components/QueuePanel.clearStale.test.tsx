import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

// ===== Mock jobStore =====
const mockUseJobStore = vi.fn()
const mockClearStale = vi.fn()

vi.mock('../../../stores/jobStore', () => ({
  useJobStore: (...args: unknown[]) => mockUseJobStore(...args),
  cancelJob: vi.fn(),
  pauseJob: vi.fn(),
  pauseQueue: vi.fn(),
  reorderQueue: vi.fn(),
  resumeJob: vi.fn(),
  resumeQueue: vi.fn(),
  clearStaleJobs: (...args: unknown[]) => mockClearStale(...args),
}))

import { QueuePanel } from './QueuePanel'

function emptyStore() {
  return {
    engine: null,
    engineLoaded: true,
    queue: {
      worker: { running: false, queue_paused: false, queue_paused_reason: null },
      running: null,
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
  mockUseJobStore.mockReturnValue(emptyStore())
})

describe('QueuePanel 清理陈旧任务（v0.13.2）', () => {
  it('点击按钮先弹二次确认（说明不删图），确认前不调 clearStaleJobs', () => {
    render(<QueuePanel />)
    fireEvent.click(screen.getByRole('button', { name: '清理陈旧任务' }))
    // 确认框出现，文案明确"不会删除已生成的图片"
    expect(screen.getByText(/把上次未正常结束的排队中.*标记为已中断.*不会删除已生成的图片/s)).toBeInTheDocument()
    expect(mockClearStale).not.toHaveBeenCalled()
  })

  it('确认后调用 clearStaleJobs 并显示"已清理 N 个陈旧任务"', async () => {
    mockClearStale.mockResolvedValue(3)
    render(<QueuePanel />)
    fireEvent.click(screen.getByRole('button', { name: '清理陈旧任务' }))
    fireEvent.click(screen.getByRole('button', { name: '清理' }))
    await waitFor(() => expect(mockClearStale).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('已清理 3 个陈旧任务')).toBeInTheDocument()
  })

  it('取消确认：不调用 clearStaleJobs', () => {
    render(<QueuePanel />)
    fireEvent.click(screen.getByRole('button', { name: '清理陈旧任务' }))
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(mockClearStale).not.toHaveBeenCalled()
  })
})
