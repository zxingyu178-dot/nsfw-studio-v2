import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ApiRequestError, imageApi } from '../../api/client'
import { ReviewMode } from './ReviewMode'
import type { ReviewSessionAdapter, SessionImage } from './hooks/useReviewSession'
import type { ImageDTO } from '../../types/workbench'
import type { ReviewSessionSummaryDTO } from '../../api/client'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {
    code: string
    status: number
    details: unknown
    constructor(code = '', message = '', status = 0, details?: unknown) {
      super(message)
      this.code = code
      this.status = status
      this.details = details
    }
  },
  imageApi: { stats: vi.fn(), get: vi.fn() },
}))

function makeSessionImage(id: string, sessionIndex: number, status: ImageDTO['status'] = 'NEW'): SessionImage {
  return {
    id,
    sessionIndex,
    job_id: 'job_1',
    job_item_id: null,
    parent_image_id: null,
    kind: 'original',
    file_path: `originals/${id}.png`,
    width: 800,
    height: 600,
    seed: 1,
    review_status: 'UNREVIEWED',
    favorite: false,
    status,
    source: 'comfyui',
    metadata: {},
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
  }
}

function makeAdapter(): ReviewSessionAdapter {
  return {
    loadPage: vi.fn(async () => ({
      items: [makeSessionImage('img_a', 0), makeSessionImage('img_b', 1)],
      has_next: false,
      total: 2,
    })),
    decideMark: vi.fn(),
    setFavorite: vi.fn(),
    resync: vi.fn(),
    reportPosition: vi.fn(),
    finish: vi.fn(async () => {}),
    getSummary: vi.fn(() => null),
    countOutsideBatch: vi.fn(async () => 0),
    startNextBatch: vi.fn(async () => {}),
  }
}

function renderMode(adapter: ReviewSessionAdapter) {
  return render(
    <MemoryRouter>
      <ReviewMode
        loader={{ loadPage: (page) => adapter.loadPage(page) }}
        sessionAdapter={adapter}
        onClose={() => {}}
        onChanged={() => {}}
      />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(imageApi.stats).mockResolvedValue({ total: 0, new: 0, keep: 0, reject: 0, archived: 0, favorites: 0 } as never)
})

describe('ReviewMode 冻结会话适配器（/api/v1/review/*）', () => {
  it('打标走 adapter.decideMark（带 sessionIndex），成功后前进', async () => {
    const adapter = makeAdapter()
    vi.mocked(adapter.decideMark).mockImplementation(async (item, action) => ({
      ...item,
      status: action,
    }) as SessionImage)
    renderMode(adapter)
    expect(await screen.findByText('1 / 2')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /保留/ }))
    await waitFor(() => expect(adapter.decideMark).toHaveBeenCalledTimes(1))
    const [item, action] = vi.mocked(adapter.decideMark).mock.calls[0]
    expect(item.id).toBe('img_a')
    expect((item as SessionImage).sessionIndex).toBe(0)
    expect(action).toBe('KEEP')
    // 自动前进到第 2 张
    expect(await screen.findByText('2 / 2')).toBeInTheDocument()
  })

  it('409 REVIEW_CONFLICT → 用权威 Image 重同步，不前进、不误计数', async () => {
    const adapter = makeAdapter()
    vi.mocked(adapter.decideMark).mockRejectedValue(
      new ApiRequestError('REVIEW_CONFLICT', '图片状态已被他处修改', 409, {
        image: { image_id: 'img_a', status: 'KEEP', is_favorite: false, updated_at: '2026-01-02T00:00:00Z' },
      }),
    )
    vi.mocked(adapter.resync).mockImplementation(async (item) => ({ ...item, status: 'KEEP' } as SessionImage))

    renderMode(adapter)
    expect(await screen.findByText('1 / 2')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /保留/ }))
    await waitFor(() => expect(adapter.resync).toHaveBeenCalled())
    // 给出同步提示
    expect(await screen.findByText(/已按最新状态同步/)).toBeInTheDocument()
    // 不前进：仍停留在第 1 张
    expect(screen.getByText('1 / 2')).toBeInTheDocument()
  })

  it('Ctrl+Z 撤销走 adapter.decideMark(NEW→RESET 语义由适配器负责)', async () => {
    const adapter = makeAdapter()
    vi.mocked(adapter.decideMark).mockImplementation(async (item, action) => ({ ...item, status: action } as SessionImage))
    renderMode(adapter)
    expect(await screen.findByText('1 / 2')).toBeInTheDocument()

    // 先保留 img_a
    fireEvent.keyDown(document, { key: 'a' })
    await waitFor(() => expect(adapter.decideMark).toHaveBeenLastCalledWith(expect.anything(), 'KEEP'))
    // 再 Ctrl+Z
    fireEvent.keyDown(document, { key: 'z', ctrlKey: true })
    await waitFor(() =>
      expect(adapter.decideMark).toHaveBeenLastCalledWith(expect.anything(), 'NEW'),
    )
  })

  it('0 张批次：显示上一批已结束 + 批次外新图，可显式换批（only_new）', async () => {
    const adapter = makeAdapter()
    vi.mocked(adapter.loadPage).mockResolvedValue({ items: [], has_next: false, total: 0 })
    vi.mocked(adapter.getSummary).mockReturnValue({
      id: 'mrs_done', status: 'COMPLETED', total_count: 0, seen_count: 0,
      current_index: 0, created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00',
      filter: {}, ended_reason: 'EMPTY',
    } as ReviewSessionSummaryDTO)
    vi.mocked(adapter.countOutsideBatch).mockResolvedValue(3)

    renderMode(adapter)
    expect(await screen.findByText('上一批审核已结束')).toBeInTheDocument()
    expect(await screen.findByText('批次之外还有 3 张待审核图片')).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: '审新图（3 张）' }))
    await waitFor(() => expect(adapter.startNextBatch).toHaveBeenCalledWith('only_new'))
  })
})
