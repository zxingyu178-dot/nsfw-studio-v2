import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { imageApi, jobApi } from '../../api/client'
import { imageThumbUrl } from '../../types/workbench'
import GalleryPage from './GalleryPage'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {},
  imageApi: {
    list: vi.fn(),
    versions: vi.fn(),
    provenance: vi.fn(),
    review: vi.fn(),
    favorite: vi.fn(),
    upscale: vi.fn(),
    workbench: vi.fn(),
    importFiles: vi.fn(),
    jobSummary: vi.fn(),
    setStatus: vi.fn(),
    cleanupRejected: vi.fn(),
  },
  jobApi: { list: vi.fn(), get: vi.fn() },
  assetApi: { create: vi.fn() },
  promptApi: { list: vi.fn() },
}))

function makeImage(id: string) {
  return {
    id,
    job_id: 'job_1',
    kind: 'original',
    source: 'GENERATE',
    review_status: 'UNREVIEWED',
    favorite: false,
    seed: 1,
    width: 800,
    height: 600,
    created_at: '2026-01-01T00:00:00',
  }
}

const PAGE1 = Array.from({ length: 40 }, (_, i) => makeImage(`img_p1_${i}`))
const PAGE2 = [makeImage('img_p2_last')]

function renderPage() {
  return render(
    <MemoryRouter>
      <GalleryPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(imageApi.list).mockImplementation(((params: { page?: number } = {}) => {
    const page = params.page ?? 1
    if (page === 1) {
      return Promise.resolve({ items: PAGE1, total: 41, page: 1, page_size: 40, has_next: true })
    }
    return Promise.resolve({ items: PAGE2, total: 41, page: 2, page_size: 40, has_next: false })
  }) as never)
  vi.mocked(imageApi.versions).mockRejectedValue(new Error('none'))
  vi.mocked(imageApi.provenance).mockRejectedValue(new Error('none'))
  vi.mocked(jobApi.list).mockResolvedValue({ items: [] } as never)
})

describe('GalleryPagination 无限滚动分页', () => {
  it('首屏只加载第一页 40 张，翻页到底再追加下一页', async () => {
    const { container } = renderPage()
    // 首屏
    await screen.findByText('共 41 张')
    expect(container.querySelectorAll('.gal-card')).toHaveLength(40)
    expect(imageApi.list).toHaveBeenCalledWith(expect.objectContaining({ page: 1, page_size: 40 }))

    // 哨兵进入视口 → 加载第二页
    ;(window as unknown as { __triggerIntersection: () => void }).__triggerIntersection()

    // 第二页已追加（40 → 41），且请求了 page=2
    await waitFor(() => expect(container.querySelectorAll('.gal-card')).toHaveLength(41))
    expect(imageApi.list).toHaveBeenCalledWith(expect.objectContaining({ page: 2, page_size: 40 }))
  })
})

describe('ThumbnailLoading 卡片缩略图懒加载', () => {
  it('进入视口前显示占位，进入后卡片使用 thumbnail URL', async () => {
    const { container } = renderPage()
    await screen.findByText('共 41 张')

    // 进入视口前：占位块存在，且卡片内无 <img>
    expect(container.querySelector('.gal-card__ph')).toBeTruthy()

    // 触发进入视口
    ;(window as unknown as { __triggerIntersection: () => void }).__triggerIntersection()

    await waitFor(() => {
      const imgs = container.querySelectorAll('.gal-card__img')
      expect(imgs.length).toBeGreaterThan(0)
      expect((imgs[0] as HTMLImageElement).getAttribute('src')).toBe(imageThumbUrl('img_p1_0'))
    })
  })
})
