import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { imageApi, jobApi } from '../../api/client'
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
  },
  jobApi: { list: vi.fn(), get: vi.fn() },
  assetApi: { create: vi.fn() },
}))

function image(id: string) {
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

const items = [image('img_a'), image('img_b'), image('img_c')]

function renderPage() {
  return render(
    <MemoryRouter>
      <GalleryPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(imageApi.list).mockResolvedValue({ items, total: items.length } as never)
  vi.mocked(imageApi.versions).mockRejectedValue(new Error('none'))
  vi.mocked(imageApi.provenance).mockRejectedValue(new Error('none'))
  vi.mocked(jobApi.list).mockResolvedValue({ items: [] } as never)
  vi.mocked(jobApi.get).mockResolvedValue({} as never)
})

describe('Gallery 单击抽屉 / 双击 Lightbox 区分', () => {
  it('单击卡片（延迟后）打开 Detail Drawer，不打开 Lightbox', async () => {
    const { container } = renderPage()
    await screen.findByText('共 3 张')
    const cards = container.querySelectorAll('.gal-card')
    expect(cards).toHaveLength(3)

    fireEvent.click(cards[1])
    // 抽屉在 ~220ms 后打开
    expect(await screen.findByText('图片详情')).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: '图片预览' })).not.toBeInTheDocument()
  })

  it('双击卡片打开 Lightbox，且不打开 / 不残留 Detail Drawer', async () => {
    const { container } = renderPage()
    await screen.findByText('共 3 张')
    const cards = container.querySelectorAll('.gal-card')

    fireEvent.click(cards[1])
    fireEvent.click(cards[1])
    fireEvent.doubleClick(cards[1])

    // Lightbox 立即打开（双击取消了抽屉定时器）
    const lightbox = await screen.findByRole('dialog', { name: '图片预览' })
    expect(lightbox).toBeInTheDocument()
    // 当前显示第二张（index 1），渐进加载默认 preview
    expect(lightbox.querySelector('img')?.getAttribute('src')).toBe('/api/v1/images/img_b/preview')
    // Detail Drawer 未打开
    expect(screen.queryByText('图片详情')).not.toBeInTheDocument()

    // 等待超过抽屉延迟时间，确认定时器已被取消、抽屉不会随后弹出
    await waitFor(() => {
      expect(screen.queryByText('图片详情')).not.toBeInTheDocument()
    }, { timeout: 500 })
    expect(screen.getByRole('dialog', { name: '图片预览' })).toBeInTheDocument()
  })

  it('Lightbox 打开期间按 ESC 关闭，且只加载当前图', async () => {
    const { container } = renderPage()
    await screen.findByText('共 3 张')
    const cards = container.querySelectorAll('.gal-card')
    fireEvent.click(cards[0])
    fireEvent.doubleClick(cards[0])

    const lightbox = await screen.findByRole('dialog', { name: '图片预览' })
    expect(lightbox.querySelectorAll('img')).toHaveLength(1)
    expect(lightbox.innerHTML).not.toContain('/api/v1/images/img_b/content')

    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: '图片预览' })).not.toBeInTheDocument()
    })
  })
})
