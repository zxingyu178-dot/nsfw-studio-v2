import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { HistoryTab } from './HistoryTab'
import type { HistoryEntryDTO, JobDTO } from '../../types/workbench'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {},
  historyApi: { list: vi.fn() },
  imageApi: { list: vi.fn(), get: vi.fn() },
  jobApi: { resumeRemaining: vi.fn(), resumeInterrupted: vi.fn() },
  moduleApi: { list: vi.fn() },
}))

function makeJob(id: string): JobDTO {
  return {
    id,
    source: 'web',
    status: 'COMPLETED',
    job_kind: 'generate',
    positive_prompt_snapshot: `prompt ${id}`,
    completed_count: 1,
    requested_count: 1,
    workflow_snapshot: { modules: [] },
    created_at: '2026-01-01T00:00:00Z',
    items: [],
    stages: [],
  } as unknown as JobDTO
}

function makeFamily(offset: number, i: number): HistoryEntryDTO {
  const root = makeJob(`job_${offset + i}`)
  return { root_job_id: root.id, root, resumes: [] }
}

describe('HistoryTab offset 分页（移除 limit=100 假全集，按 root family）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('加载更多取回 offset=30 / 60，越过 100 条上限可达 70 个任务族', async () => {
    const { historyApi } = await import('../../api/client')
    // 共 70 个任务族，每页 30
    vi.mocked(historyApi.list).mockImplementation((params: { offset?: number } = {}) => {
      const offset = params.offset ?? 0
      const limit = 30
      const size = Math.min(limit, 70 - offset)
      const items = Array.from({ length: size }, (_, i) => makeFamily(offset, i))
      return Promise.resolve({ items, total: 70, limit, offset }) as never
    })

    const { container } = render(
      <MemoryRouter>
        <HistoryTab />
      </MemoryRouter>,
    )

    // 第一页：30 个 root family（resumes 为空 → 每张 root family = 1 张卡片）
    await waitFor(() => expect(container.querySelectorAll('.pp-hist-card').length).toBe(30))
    expect(historyApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 30, offset: 0 }))

    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    await waitFor(() => expect(container.querySelectorAll('.pp-hist-card').length).toBe(60))
    expect(historyApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 30, offset: 30 }))

    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    await waitFor(() => expect(container.querySelectorAll('.pp-hist-card').length).toBe(70))
    expect(historyApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 30, offset: 60 }))

    await waitFor(() => expect(screen.getByText('已加载全部 70 个任务族')).toBeInTheDocument())
  })

  it('继续全部中断任务后显示结果并重新加载历史', async () => {
    const { historyApi, jobApi } = await import('../../api/client')
    vi.mocked(historyApi.list).mockResolvedValue({ items: [], total: 0, limit: 30, offset: 0 } as never)
    vi.mocked(jobApi.resumeInterrupted).mockResolvedValue({
      requeued: [],
      resumed: [],
      skipped: [],
      errors: [],
      requeued_count: 0,
      resumed_count: 0,
      remaining_images: 0,
    } as never)

    const { container } = render(
      <MemoryRouter>
        <HistoryTab />
      </MemoryRouter>,
    )

    await waitFor(() => expect(historyApi.list).toHaveBeenCalledTimes(1))
    fireEvent.click(screen.getByRole('button', { name: '继续全部中断任务' }))

    await waitFor(() => expect(jobApi.resumeInterrupted).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('已恢复 0 个任务，剩余 0 张')).toBeInTheDocument()
    expect(container.querySelector('.ds-notice--error')).not.toBeInTheDocument()
    await waitFor(() => expect(historyApi.list).toHaveBeenCalledTimes(2))
  })
})
