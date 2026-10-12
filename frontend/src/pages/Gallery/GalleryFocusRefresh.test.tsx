import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { imageApi, jobApi } from '../../api/client'
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
})
