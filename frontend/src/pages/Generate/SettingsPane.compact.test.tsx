import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const mockUseJobStore = vi.fn()
const mockPauseQueue = vi.fn()

vi.mock('../../stores/jobStore', () => ({
  useJobStore: (...args: unknown[]) => mockUseJobStore(...args),
  activeJob: vi.fn(() => null),
  cancelJob: vi.fn(),
  pauseJob: vi.fn(),
  pauseQueue: (...args: unknown[]) => mockPauseQueue(...args),
  reorderQueue: vi.fn(),
  resumeJob: vi.fn(),
  resumeQueue: vi.fn(),
  resumeRemaining: vi.fn(),
  submitGeneration: vi.fn(),
}))

import { SettingsPane } from './SettingsPane'

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

/** 构造 ≥20 个 queued job 的 store。 */
function storeWithManyQueued(count: number) {
  const queued = Array.from({ length: count }, (_, i) => queuedJob(i))
  return {
    engine: null,
    engineLoaded: true,
    queue: {
      worker: { running: true, queue_paused: false, queue_paused_reason: null },
      running: { id: 'job_running_1' },
      queued,
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

describe('SettingsPane 紧凑队列（固定高度内部滚动）', () => {
  it('≥20 个排队任务时，队列列表为固定 max-height + overflow 内部滚动', () => {
    mockUseJobStore.mockReturnValue(storeWithManyQueued(24))
    const { container } = render(<SettingsPane imageGenAvailable={true} />)

    const list = container.querySelector('.wb-queue-list') as HTMLElement
    expect(list).toBeInTheDocument()
    // 固定高度 + 内部滚动（内联样式，jsdom 可断言）
    expect(list.style.maxHeight).toBe('300px')
    expect(list.style.overflowY).toBe('auto')
    expect(list).toHaveClass('wb-queue-list--scroll')

    // 24 行全部渲染（滚动只在容器内部发生，不撑高右栏）
    expect(container.querySelectorAll('.wb-queue-item')).toHaveLength(24)
  })

  it('保留拖拽属性与行内控件（优先/暂停/取消），标题与暂停队列按钮在滚动区外', () => {
    mockUseJobStore.mockReturnValue(storeWithManyQueued(22))
    const { container } = render(<SettingsPane imageGenAvailable={true} />)

    // queued 行可拖拽
    const draggableRows = container.querySelectorAll('.wb-queue-list li[draggable="true"]')
    expect(draggableRows.length).toBe(22)

    // 行内控件仍存在
    expect(screen.getAllByRole('button', { name: '暂停' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: '取消' }).length).toBeGreaterThan(0)
    // index>0 的行有“优先”
    expect(screen.getAllByRole('button', { name: '优先' }).length).toBe(21)

    // 标题与队列暂停按钮固定在滚动区外（.wb-queue-list 之外）
    expect(container.querySelector('.wb-queue__title')?.textContent).toBe('队列')
    const pauseAll = screen.getByRole('button', { name: '暂停队列' })
    expect(pauseAll).toBeInTheDocument()
    expect(container.querySelector('.wb-queue-list')).not.toContainElement(pauseAll)

    // 暂停队列按钮仍可用
    fireEvent.click(pauseAll)
    expect(mockPauseQueue).toHaveBeenCalledTimes(1)
  })
})
