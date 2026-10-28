import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { imageApi, jobApi } from '../../api/client'
import type { ImageDTO } from '../../types/workbench'
import GalleryPage from './GalleryPage'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {},
  imageApi: {
    list: vi.fn(),
    stats: vi.fn(),
    versions: vi.fn(),
    provenance: vi.fn(),
    review: vi.fn(),
    favorite: vi.fn(),
    upscale: vi.fn(),
    workbench: vi.fn(),
    importFiles: vi.fn(),
    jobSummary: vi.fn(),
    jobGroups: vi.fn(),
    setStatus: vi.fn(),
    cleanupRejected: vi.fn(),
  },
  jobApi: { list: vi.fn(), get: vi.fn() },
  assetApi: { create: vi.fn() },
  promptApi: { list: vi.fn() },
}))

function setVisibility(state: 'visible' | 'hidden'): void {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(imageApi.list).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 40, has_next: false } as never)
  vi.mocked(imageApi.stats).mockResolvedValue({ total: 0, new: 0, keep: 0, reject: 0, archived: 0, favorites: 0 } as never)
  vi.mocked(imageApi.versions).mockRejectedValue(new Error('none'))
  vi.mocked(imageApi.provenance).mockRejectedValue(new Error('none'))
  vi.mocked(imageApi.jobGroups).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, has_next: false } as never)
  vi.mocked(jobApi.list).mockResolvedValue({ items: [] } as never)
})

function image(id: string): ImageDTO {
  return {
    id,
    job_id: 'job_1',
    job_item_id: null,
    parent_image_id: null,
    kind: 'original',
    file_path: `images/${id}.png`,
    width: 512,
    height: 512,
    seed: 1,
    review_status: 'UNREVIEWED',
    favorite: false,
    status: 'NEW',
    source: 'comfyui',
    metadata: {},
    created_at: '2026-10-20T00:00:00Z',
    updated_at: '2026-10-20T00:00:00Z',
  }
}

describe('GalleryFocusRefresh（T18 联合刷新：无 SSE / 无高频轮询）', () => {
  it('window focus → 静默重拉首页 page=1 + stats', async () => {
    render(
      <MemoryRouter>
        <GalleryPage />
      </MemoryRouter>,
    )
    await screen.findByText('共 0 张')
    const callsAfterMount = vi.mocked(imageApi.list).mock.calls.length
    const statsAfterMount = vi.mocked(imageApi.stats).mock.calls.length

    window.dispatchEvent(new Event('focus'))
    await waitFor(() =>
      expect(vi.mocked(imageApi.list).mock.calls.length).toBeGreaterThan(callsAfterMount),
    )
    // 重拉的是首页（page 1），不是追加页
    expect(vi.mocked(imageApi.list).mock.lastCall?.[0]).toMatchObject({ page: 1 })
    // stats 同步刷新
    expect(vi.mocked(imageApi.stats).mock.calls.length).toBeGreaterThan(statsAfterMount)
  })

  it('visibilitychange→visible → 重拉首页 + stats；hidden → 不触发', async () => {
    render(
      <MemoryRouter>
        <GalleryPage />
      </MemoryRouter>,
    )
    await screen.findByText('共 0 张')

    // hidden：不触发重拉
    setVisibility('hidden')
    document.dispatchEvent(new Event('visibilitychange'))
    await new Promise((r) => setTimeout(r, 300))
    const hiddenCalls = vi.mocked(imageApi.list).mock.calls.length

    // visible：触发重拉
    setVisibility('visible')
    document.dispatchEvent(new Event('visibilitychange'))
    await waitFor(() =>
      expect(vi.mocked(imageApi.list).mock.calls.length).toBeGreaterThan(hiddenCalls),
    )
    expect(vi.mocked(imageApi.list).mock.lastCall?.[0]).toMatchObject({ page: 1 })
  })

  it('深页浏览时新图只提示数量，点击后增量并入且不清空已加载列表', async () => {
    vi.mocked(imageApi.list)
      .mockResolvedValueOnce({ items: [image('a'), image('b')], total: 2, page: 1, page_size: 40, has_next: false } as never)
      .mockResolvedValue({ items: [image('n'), image('a'), image('b')], total: 3, page: 1, page_size: 40, has_next: false } as never)

    Object.defineProperty(window, 'scrollY', { value: 900, configurable: true })
    const { container } = render(
      <MemoryRouter>
        <GalleryPage />
      </MemoryRouter>,
    )
    await screen.findByText('共 2 张')

    window.dispatchEvent(new Event('focus'))
    await screen.findByText(/有 1 张新图/)

    // 已加载卡片未被重置，也没有被静默重排
    expect(container.querySelectorAll('[data-image-id]')).toHaveLength(2)

    fireEvent.click(screen.getByRole('button', { name: '点击刷新' }))
    await waitFor(() =>
      expect(container.querySelectorAll('[data-image-id]')).toHaveLength(3),
    )
    expect(screen.queryByText(/有 1 张新图/)).toBeNull()
    expect(container.querySelector('[data-image-id="n"]')).toBeTruthy()
  })
})
