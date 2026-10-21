import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { imageApi, jobApi } from '../../api/client'
import GalleryPage from './GalleryPage'
import { ReviewMode } from './ReviewMode'
import { ImageLightbox } from '../../components/ImageLightbox'
import type { ImageDTO } from '../../types/workbench'

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
    jobGroups: vi.fn(),
    stats: vi.fn(),
    setStatus: vi.fn(),
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

function makeImage(id: string, status: ImageDTO['status'] = 'NEW', favorite = false): ImageDTO {
  return {
    id,
    job_id: 'job_1',
    job_item_id: null,
    parent_image_id: null,
    kind: 'original',
    file_path: `originals/${id}.png`,
    width: 800,
    height: 600,
    seed: 1,
    review_status: 'UNREVIEWED',
    favorite,
    status,
    source: 'comfyui',
    metadata: {},
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
  } as ImageDTO
}

function renderPage() {
  return render(
    <MemoryRouter>
      <GalleryPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(imageApi.list).mockResolvedValue({ items: [], total: 0 } as never)
  vi.mocked(imageApi.versions).mockRejectedValue(new Error('none'))
  vi.mocked(imageApi.provenance).mockRejectedValue(new Error('none'))
  vi.mocked(imageApi.jobGroups).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20, has_next: false } as never)
  vi.mocked(jobApi.list).mockResolvedValue({ items: [] } as never)
  vi.mocked(imageApi.stats).mockResolvedValue({ total: 10, new: 7, keep: 2, reject: 1, archived: 0, favorites: 3 } as never)
  vi.mocked(imageApi.setStatus).mockImplementation((id, body) =>
    Promise.resolve({ ...makeImage(id), status: body.status } as ImageDTO),
  )
  vi.mocked(imageApi.favorite).mockImplementation((id, fav) =>
    Promise.resolve({ ...makeImage(id), favorite: fav } as ImageDTO),
  )
})

describe('Gallery UX 2.0：两层 Toolbar', () => {
  it('第一层浏览 tabs 与第二层筛选控件同时存在', () => {
    renderPage()
    // 第一层：浏览模式 tabs
    expect(screen.getByText('全部')).toBeInTheDocument()
    expect(screen.getByText('待审核')).toBeInTheDocument()
    expect(screen.getByText('收藏')).toBeInTheDocument()
    expect(screen.getByText('归档')).toBeInTheDocument()
    // 第二层：筛选 selects
    expect(screen.getByLabelText('网格密度')).toBeInTheDocument()
    expect(screen.getByLabelText('排序')).toBeInTheDocument()
    // 适应/填充已移除：图片始终按原始比例完整显示
    expect(screen.queryByRole('button', { name: '适应' })).toBeNull()
    expect(screen.queryByRole('button', { name: '填充' })).toBeNull()
  })
})

describe('Gallery UX 2.0：密度偏好', () => {
  it('默认 normal 网格修饰类', async () => {
    vi.mocked(imageApi.list).mockResolvedValue({ items: [baseImage], total: 1 } as never)
    const { container } = renderPage()
    await screen.findByText('共 1 张')
    const grid = container.querySelector('.gal-grid') as HTMLElement
    expect(grid.className).toContain('gal-grid--normal')
  })

  it('切换密度为 compact 后网格修饰类随之更新', async () => {
    vi.mocked(imageApi.list).mockResolvedValue({ items: [baseImage], total: 1 } as never)
    const { container } = renderPage()
    await screen.findByText('共 1 张')

    fireEvent.change(screen.getByLabelText('网格密度'), { target: { value: 'compact' } })
    const grid = container.querySelector('.gal-grid') as HTMLElement
    expect(grid.className).toContain('gal-grid--compact')
    expect(localStorage.getItem('gallery.density')).toBe('compact')
  })
})

describe('Review Mode 2.0：全局统计', () => {
  it('传入 statsParams 后显示 server 端剩余待审 N', async () => {
    render(
      <MemoryRouter>
        <ReviewMode images={[makeImage('img_a')]} statsParams={{ status: 'NEW' }} onClose={() => {}} onChanged={() => {}} />
      </MemoryRouter>,
    )
    expect(imageApi.stats).toHaveBeenCalled()
    expect(await screen.findByText(/剩余待审 7/)).toBeInTheDocument()
  })
})

describe('Review Mode 2.0：Ctrl+Z 撤销', () => {
  it('打标后 Ctrl+Z 恢复到上一条之前的状态', async () => {
    render(
      <MemoryRouter>
        <ReviewMode images={[makeImage('img_a'), makeImage('img_b'), makeImage('img_c')]} onClose={() => {}} onChanged={() => {}} />
      </MemoryRouter>,
    )
    fireEvent.keyDown(document, { key: 'a' })
    await waitFor(() => expect(imageApi.setStatus).toHaveBeenCalledWith('img_a', { status: 'KEEP' }))
    // Ctrl+Z 撤销：恢复 img_a 打标前（NEW）
    fireEvent.keyDown(document, { key: 'z', ctrlKey: true })
    await waitFor(() =>
      expect(imageApi.setStatus).toHaveBeenCalledWith('img_a', { status: 'NEW' }),
    )
  })
})

describe('Review Mode 2.0：跨分页预取', () => {
  it('接近末尾时预取下一页，进度随加载累计', async () => {
    const page1 = [makeImage('a'), makeImage('b'), makeImage('c')]
    const page2 = [makeImage('d'), makeImage('e')]
    const loader = {
      loadPage: vi.fn(async (page: number) =>
        page === 1
          ? { items: page1, has_next: true, total: 5 }
          : { items: page2, has_next: false, total: 5 },
      ),
    }
    render(
      <MemoryRouter>
        <ReviewMode loader={loader} onClose={() => {}} onChanged={() => {}} />
      </MemoryRouter>,
    )
    expect(await screen.findByText('1 / 5')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'ArrowRight' })
    fireEvent.keyDown(document, { key: 'ArrowRight' })
    expect(await screen.findByText('3 / 5')).toBeInTheDocument()
    // 预取加载第二页
    await waitFor(() => expect(loader.loadPage).toHaveBeenCalledWith(2))
  })
})

describe('Lightbox：跨分页加载', () => {
  it('到末尾按下一张触发 onLoadMore（append 下一页）', () => {
    const onLoadMore = vi.fn()
    render(
      <MemoryRouter>
        <ImageLightbox
          images={[
            { id: 'a', width: 100, height: 100, kind: 'original' },
            { id: 'b', width: 100, height: 100, kind: 'original' },
          ]}
          index={1}
          hasMore
          onLoadMore={onLoadMore}
          onClose={() => {}}
          onNavigate={() => {}}
        />
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByRole('button', { name: /加载更多|下一张/ }))
    expect(onLoadMore).toHaveBeenCalledTimes(1)
  })
})

describe('Lightbox：信息栏折叠', () => {
  it('点击隐藏信息后右侧信息栏消失，再点显示信息恢复', () => {
    render(
      <MemoryRouter>
        <ImageLightbox
          images={[{ id: 'a', width: 100, height: 100, kind: 'original' }]}
          index={0}
          onClose={() => {}}
          onNavigate={() => {}}
          renderSidePanel={() => <div data-testid="side-panel">PANEL</div>}
        />
      </MemoryRouter>,
    )
    expect(screen.getByTestId('side-panel')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '隐藏信息' }))
    expect(screen.queryByTestId('side-panel')).not.toBeInTheDocument()
    // 偏好持久化：隐藏态写入 localStorage
    expect(localStorage.getItem('lightbox.infoHidden')).toBe('1')
    fireEvent.click(screen.getByRole('button', { name: '显示信息' }))
    expect(screen.getByTestId('side-panel')).toBeInTheDocument()
  })
})
