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

const baseImage = {
  id: 'img_1',
  job_id: null,
  kind: 'generated',
  source: 'GENERATE',
  review_status: 'UNREVIEWED',
  favorite: false,
  seed: 123,
  width: 512,
  height: 768,
  created_at: '2026-01-01T00:00:00',
}

function renderPage() {
  return render(
    <MemoryRouter>
      <GalleryPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.mocked(imageApi.list).mockResolvedValue({ items: [], total: 0 } as never)
  vi.mocked(imageApi.versions).mockRejectedValue(new Error('none'))
  vi.mocked(imageApi.provenance).mockRejectedValue(new Error('none'))
  vi.mocked(jobApi.list).mockResolvedValue({ items: [] } as never)
})

describe('GalleryPage 图库', () => {
  it('渲染五个筛选标签与工具按钮', () => {
    renderPage()
    expect(screen.getByText('全部')).toBeInTheDocument()
    expect(screen.getByText('未审核')).toBeInTheDocument()
    expect(screen.getByText('保留')).toBeInTheDocument()
    expect(screen.getByText('收藏')).toBeInTheDocument()
    expect(screen.getByText('淘汰')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '选择' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '按任务查看' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '导入' })).toBeInTheDocument()
  })

  it('无图片时显示空状态', async () => {
    renderPage()
    expect(await screen.findByText('还没有图片')).toBeInTheDocument()
  })

  it('有图片时显示数量，点击卡片打开详情抽屉', async () => {
    vi.mocked(imageApi.list).mockResolvedValue({ items: [baseImage], total: 1 } as never)
    const { container } = renderPage()

    expect(await screen.findByText('共 1 张')).toBeInTheDocument()
    const card = container.querySelector('.gal-card') as HTMLButtonElement
    fireEvent.click(card)

    expect(await screen.findByText('图片详情')).toBeInTheDocument()
    // 详情抽屉内的审核操作
    expect(screen.getByRole('button', { name: '保留 (K)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '淘汰 (R)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '☆ 收藏 (F)' })).toBeInTheDocument()
  })

  it('进入选择模式后显示高清放大操作', async () => {
    vi.mocked(imageApi.list).mockResolvedValue({ items: [baseImage], total: 1 } as never)
    renderPage()
    await screen.findByText('共 1 张')

    fireEvent.click(screen.getByRole('button', { name: '选择' }))
    expect(screen.getByText('已选 0 张')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '高清放大' })).toBeDisabled()
  })

  it('切换到按任务查看时加载任务分组', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: '按任务查看' }))
    await waitFor(() => expect(jobApi.list).toHaveBeenCalled())
  })
})
