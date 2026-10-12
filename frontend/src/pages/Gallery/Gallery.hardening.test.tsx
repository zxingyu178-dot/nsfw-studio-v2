import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { imageApi, jobApi, promptApi } from '../../api/client'
import GalleryPage from './GalleryPage'
import { ReviewMode } from './ReviewMode'
import type { ImageDTO } from '../../types/workbench'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {},
  imageApi: {
    list: vi.fn(),
    versions: vi.fn(),
    provenance: vi.fn(),
    review: vi.fn(),
    favorite: vi.fn(),
    setStatus: vi.fn(),
    upscale: vi.fn(),
    workbench: vi.fn(),
    importFiles: vi.fn(),
    jobSummary: vi.fn(),
    jobGroups: vi.fn(),
    cleanupRejected: vi.fn(),
  },
  jobApi: { list: vi.fn(), get: vi.fn() },
  assetApi: { create: vi.fn() },
  promptApi: { list: vi.fn(), setPreviewImage: vi.fn() },
}))

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
    review_status: status === 'KEEP' ? 'KEPT' : status === 'REJECT' ? 'REJECTED' : 'UNREVIEWED',
    favorite,
    status,
    source: 'comfyui',
    metadata: {},
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <GalleryPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(imageApi.versions).mockRejectedValue(new Error('none'))
  vi.mocked(imageApi.provenance).mockRejectedValue(new Error('none'))
  vi.mocked(jobApi.list).mockResolvedValue({ items: [] } as never)
  vi.mocked(jobApi.get).mockResolvedValue({} as never)
  vi.mocked(promptApi.list).mockResolvedValue({ items: [] } as never)
})

describe('分页竞态：切筛选后 stale page 不污染新列表', () => {
  it('page2 未完成时切到“收藏”，旧 page2 返回后不混入新收藏列表', async () => {
    const P1 = Array.from({ length: 40 }, (_, i) => makeImage(`p1_${i}`))
    const FAV1 = [makeImage('fav_a', 'KEEP', true), makeImage('fav_b', 'KEEP', true)]
    const STALE = makeImage('stale_old')

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let resolvePage2: (v: any) => void = () => {}
    vi.mocked(imageApi.list).mockImplementation((rawParams) => {
      const params = (rawParams ?? {}) as { page?: number; favorite?: boolean }
      if (params.favorite) {
        return Promise.resolve({ items: FAV1, total: FAV1.length, page: 1, page_size: 40, has_next: false })
      }
      if ((params.page ?? 1) === 1) {
        return Promise.resolve({ items: P1, total: P1.length + 1, page: 1, page_size: 40, has_next: true })
      }
      // page 2：挂起，直到测试手动 resolve
      return new Promise((resolve) => { resolvePage2 = resolve })
    })

    const { container } = renderPage()
    await screen.findByText('共 41 张')
    expect(container.querySelectorAll('.gal-card')).toHaveLength(40)

    // 触发无限滚动 → page2 请求挂起
    ;(window as unknown as { __triggerIntersection: () => void }).__triggerIntersection()
    await waitFor(() =>
      expect(imageApi.list).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })),
    )

    // 切到“收藏”Tab → loadFirst 新请求（新 requestSeq）
    fireEvent.click(screen.getByRole('tab', { name: '收藏' }))
    await waitFor(() => expect(container.querySelectorAll('.gal-card')).toHaveLength(2))

    // 旧 page2 此刻才返回 → 不得 append 到收藏列表
    resolvePage2({ items: [STALE], total: 42, page: 2, page_size: 40, has_next: false })
    await new Promise((r) => setTimeout(r, 50))

    // 收藏列表仍为 2 张（stale 旧筛选结果被丢弃）
    expect(container.querySelectorAll('.gal-card')).toHaveLength(2)
  })
})

describe('清理 UI：deletable/protected/原因与删除门槛', () => {
  it('预览展示 deletable 数量与 protected 原因摘要；确认按钮按 deletable 计数', async () => {
    vi.mocked(imageApi.list).mockResolvedValue({ items: [makeImage('img_1')], total: 1, page: 1, page_size: 40, has_next: false } as never)
    vi.mocked(imageApi.cleanupRejected).mockResolvedValue({
      candidate_count: 10,
      deletable_count: 4,
      protected_count: 6,
      total_bytes: 2048,
      protected_items: [{ image_id: 'img_prot', reasons: ['被 Prompt 引用', '被素材引用'] }],
    } as never)

    renderPage()
    await screen.findByText('共 1 张')
    fireEvent.click(screen.getByRole('button', { name: '清理废片' }))

    await screen.findByText('实际可删')
    expect(screen.getByText('4 张')).toBeInTheDocument()
    // protected 原因可展开查看
    expect(screen.getByText(/被 Prompt 引用/)).toBeInTheDocument()
    // 确认按钮显示 deletable 数而非 candidate 总数
    expect(screen.getByRole('button', { name: /确认删除 4 张/ })).toBeInTheDocument()
  })

  it('deletable_count=0 时确认按钮禁用', async () => {
    vi.mocked(imageApi.list).mockResolvedValue({ items: [makeImage('img_1')], total: 1, page: 1, page_size: 40, has_next: false } as never)
    vi.mocked(imageApi.cleanupRejected).mockResolvedValue({
      candidate_count: 10,
      deletable_count: 0,
      protected_count: 10,
      total_bytes: 0,
      protected_items: [{ image_id: 'img_prot', reasons: ['被引用'] }],
    } as never)

    renderPage()
    await screen.findByText('共 1 张')
    fireEvent.click(screen.getByRole('button', { name: '清理废片' }))
    await screen.findByText('实际可删')
    expect(screen.getByRole('button', { name: /确认删除/ })).toBeDisabled()
  })
})

describe('ReviewMode 分页会话：末尾预取 + 服务端 total 进度', () => {
  it('接近末尾预取下一页，统计随加载累计', async () => {
    const page1 = [makeImage('r_a', 'KEEP'), makeImage('r_b'), makeImage('r_c', 'REJECT')]
    const page2 = [makeImage('r_d'), makeImage('r_e', 'KEEP', true)]
    const loadedPages: number[] = []
    render(
      <MemoryRouter>
        <ReviewMode
          title="图库审核"
          onClose={() => {}}
          loader={{
            loadPage: (page) => {
              loadedPages.push(page)
              if (page === 1) return Promise.resolve({ items: page1, has_next: true, total: 5 })
              return Promise.resolve({ items: page2, has_next: false, total: 5 })
            },
          }}
        />
      </MemoryRouter>,
    )

    // 服务端 total 作为分母
    await screen.findByText(/1 \/ 5/)
    // 切到接近末尾（index 2）→ 触发预取 page2
    fireEvent.keyDown(document, { key: 'ArrowRight' })
    fireEvent.keyDown(document, { key: 'ArrowRight' })
    await waitFor(() => expect(loadedPages).toContain(2))
    // 预取后列表已加载到 5 张，当前停在第 3 张
    expect(screen.getByText(/3 \/ 5/)).toBeInTheDocument()
  })
})

describe('Job Review：取消 page_size=100 上限，分页拉全', () => {
  it('从分组开始审核后按 job_id 逐页拉取直到 has_next=false', async () => {
    const groups = [{
      job_id: 'job_abc', module_id: 'basic_generate', created_at: '2026-01-01T00:00:00',
      total: 250, unreviewed: 200, kept: 40, rejected: 10, favorites: 5,
    }]
    vi.mocked(imageApi.jobGroups).mockResolvedValue({ items: groups, total: 1, page: 1, page_size: 20, has_next: false } as never)

    const loadedPages: number[] = []
    vi.mocked(imageApi.list).mockImplementation((rawParams) => {
      const params = (rawParams ?? {}) as { job_id?: string; page?: number }
      const page = params.page ?? 1
      loadedPages.push(page)
      // 每页 3 张，便于快速触发“接近末尾预取”；>100 的 Job 靠分页拉全
      if (page <= 3) {
        return Promise.resolve({ items: Array.from({ length: 3 }, (_, i) => makeImage(`job_${page}_${i}`)), total: 250, page, page_size: 40, has_next: true })
      }
      return Promise.resolve({ items: [makeImage('job_last')], total: 250, page: 4, page_size: 40, has_next: false })
    })

    renderPage()
    // 进入按任务查看
    fireEvent.click(screen.getByRole('button', { name: '按任务查看' }))
    await screen.findByText(/未审核 200/)

    // 点击该 Job 的“开始审核”（工具栏也有一个同名按钮，取分组内的）
    const reviewButtons = screen.getAllByRole('button', { name: '开始审核' })
    fireEvent.click(reviewButtons[reviewButtons.length - 1])
    // 进入 Review Session（按 job_id），首屏一页
    await screen.findByText(/1 \/ 250/)
    // 前进到接近末尾 → 预取下一页（证明取消了 page_size=100 上限，分页拉全）
    fireEvent.keyDown(document, { key: 'ArrowRight' })
    fireEvent.keyDown(document, { key: 'ArrowRight' })
    await waitFor(() => expect(loadedPages).toContain(2))
    expect(imageApi.list).toHaveBeenCalledWith(expect.objectContaining({ job_id: 'job_abc', page: 1 }))
  })
})
