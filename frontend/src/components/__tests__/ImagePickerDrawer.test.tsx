import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { imageApi } from '../../api/client'
import { imageThumbUrl, type ImageDTO } from '../../types/workbench'
import { ImagePickerDrawer } from '../ImagePickerDrawer'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {},
  imageApi: { list: vi.fn() },
}))

function makeImage(id: string, favorite = false): ImageDTO {
  return {
    id,
    job_id: 'job_1',
    job_item_id: 'ji_1',
    parent_image_id: null,
    kind: 'original',
    file_path: `/x/${id}.png`,
    width: 800,
    height: 600,
    seed: 1,
    review_status: 'UNREVIEWED',
    favorite,
    source: 'GENERATE',
    metadata: {},
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
  }
}

function renderDrawer(onPicked = vi.fn()) {
  return render(<ImagePickerDrawer onClose={vi.fn()} onPicked={onPicked} />)
}

function triggerIntersection() {
  ;(window as unknown as { __triggerIntersection: (v?: boolean) => void }).__triggerIntersection(true)
}

const cards = (container: HTMLElement) => container.querySelectorAll('.wb-image-item')

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ImagePickerDrawer 分页 + 无限滚动', () => {
  it('首屏加载第一页 40 张，哨兵触发后追加第二页', async () => {
    const page1 = Array.from({ length: 40 }, (_, i) => makeImage(`p1_${i}`))
    const page2 = [makeImage('p2_0')]
    vi.mocked(imageApi.list).mockImplementation(((params: { page?: number } = {}) => {
      const page = params.page ?? 1
      if (page === 1) return Promise.resolve({ items: page1, total: 41, page: 1, page_size: 40, has_next: true })
      return Promise.resolve({ items: page2, total: 41, page: 2, page_size: 40, has_next: false })
    }) as never)

    const { container } = renderDrawer()

    await waitFor(() => expect(cards(container)).toHaveLength(40))
    expect(imageApi.list).toHaveBeenCalledWith(expect.objectContaining({ page: 1, page_size: 40 }))

    triggerIntersection()

    await waitFor(() => expect(cards(container)).toHaveLength(41), { timeout: 4000 })
    expect(imageApi.list).toHaveBeenCalledWith(expect.objectContaining({ page: 2, page_size: 40 }))
  })

  it('网格卡片使用缩略图 URL，不使用原图 content', async () => {
    const page1 = [makeImage('thumb_a'), makeImage('thumb_b')]
    vi.mocked(imageApi.list).mockResolvedValue({
      items: page1,
      total: 2,
      page: 1,
      page_size: 40,
      has_next: false,
    } as never)

    const { container } = renderDrawer()
    await waitFor(() => expect(cards(container)).toHaveLength(2))

    const imgs = container.querySelectorAll('.wb-image-item img')
    expect(imgs).toHaveLength(2)
    expect((imgs[0] as HTMLImageElement).getAttribute('src')).toBe(imageThumbUrl('thumb_a'))
    expect(container.innerHTML).not.toContain('/content')
  })
})

describe('ImagePickerDrawer 筛选参数映射', () => {
  it('四个 Tab 分别发出正确的 status / favorite / sort 参数', async () => {
    vi.mocked(imageApi.list).mockImplementation(((params: { page?: number } = {}) => {
      const page = params.page ?? 1
      return Promise.resolve({
        items: page === 1 ? [makeImage('x')] : [],
        total: 1,
        page,
        page_size: 40,
        has_next: false,
      })
    }) as never)

    renderDrawer()

    const listMock = vi.mocked(imageApi.list)

    // 最近：不带 status / favorite，sort=created_desc
    await waitFor(() => expect(listMock).toHaveBeenCalled())
    const recent = listMock.mock.calls[listMock.mock.calls.length - 1]![0]!
    expect(recent).toMatchObject({ sort: 'created_desc', page: 1, page_size: 40 })
    expect(recent.status).toBeUndefined()
    expect(recent.favorite).toBeUndefined()

    // 未审核：status=NEW
    fireEvent.click(screen.getByRole('tab', { name: '未审核' }))
    await waitFor(() => {
      const c = listMock.mock.calls.at(-1)![0]
      expect(c).toMatchObject({ status: 'NEW', page: 1 })
    })

    // 保留：status=KEEP
    fireEvent.click(screen.getByRole('tab', { name: '保留' }))
    await waitFor(() => {
      const c = listMock.mock.calls.at(-1)![0]
      expect(c).toMatchObject({ status: 'KEEP', page: 1 })
    })

    // 收藏：favorite=true，且不得把 status 设成 FAVORITE
    fireEvent.click(screen.getByRole('tab', { name: '收藏' }))
    await waitFor(() => {
      const c = listMock.mock.calls.at(-1)![0]
      expect(c).toMatchObject({ favorite: true, page: 1 })
    })
    const fav = listMock.mock.calls.at(-1)![0]!
    expect(fav.status).toBeUndefined()
    expect(fav.status).not.toBe('FAVORITE')
  })
})

describe('ImagePickerDrawer 历史可达（越过 120 张）', () => {
  it('多页连续追加直到最早一张，has_next 最终 false、无重无漏', async () => {
    // 4 页 × 40 + 20 = 140 张（>120），前 3 页 has_next=true，末页 false
    const totalPages = 4
    vi.mocked(imageApi.list).mockImplementation(((params: { page?: number } = {}) => {
      const page = params.page ?? 1
      const size = page < totalPages ? 40 : 20
      const items = Array.from({ length: size }, (_, i) => makeImage(`p${page}_${i}`))
      return Promise.resolve({
        items,
        total: 140,
        page,
        page_size: 40,
        has_next: page < totalPages,
      })
    }) as never)

    const { container } = renderDrawer()

    // 逐次触发哨兵，直到没有更多页
    for (let i = 0; i < totalPages + 2; i++) {
      triggerIntersection()
      // 给追加留时间；若已到底，触发无副作用
      await waitFor(() => {}, { timeout: 10 }).catch(() => {})
      // eslint-disable-next-line no-await-in-loop
      await new Promise((r) => setTimeout(r, 60))
    }

    await waitFor(() => expect(cards(container)).toHaveLength(140), { timeout: 8000 })

    // 请求到了第 4 页（最早一批），之后不再请求第 5 页
    const pagesCalled = vi.mocked(imageApi.list).mock.calls.map((c) => (c[0] as { page: number }).page)
    expect(Math.max(...pagesCalled)).toBe(4)
    expect(pagesCalled).not.toContain(5)

    // 无重无漏：收集所有渲染出来的图片 id 应去重后等于 140
    const ids = Array.from(container.querySelectorAll('.wb-image-item img')).map((im) =>
      (im as HTMLImageElement).getAttribute('src'),
    )
    expect(new Set(ids).size).toBe(140)
  })
})

describe('ImagePickerDrawer 请求竞态守卫', () => {
  it('切换筛选后，旧筛选晚返回的请求不污染新列表', async () => {
    const inflight: { params: Record<string, unknown>; resolve: (v: any) => void }[] = []
    vi.mocked(imageApi.list).mockImplementation(((params: Record<string, unknown> = {}) => {
      return new Promise((resolve) => {
        inflight.push({ params, resolve: resolve as (v: any) => void })
      })
    }) as never)

    const { container } = renderDrawer()

    // 等待首个（RECENT）请求发出
    await waitFor(() => expect(inflight.length).toBe(1))
    expect(inflight[0].params).toMatchObject({ page: 1 })

    // 切到「保留」→ 触发新 generation；此时 RECENT 请求仍在途
    fireEvent.click(screen.getByRole('tab', { name: '保留' }))
    await waitFor(() => expect(inflight.length).toBe(2))
    expect(inflight[1].params).toMatchObject({ status: 'KEEP', page: 1 })

    // 旧 RECENT 请求此时才返回 —— 必须被忽略
    inflight[0].resolve({
      items: [makeImage('stale_a'), makeImage('stale_b')],
      total: 2,
      page: 1,
      page_size: 40,
      has_next: false,
    })
    await new Promise((r) => setTimeout(r, 20))
    expect(container.querySelectorAll('img[src*="stale_a"]')).toHaveLength(0)
    expect(container.querySelectorAll('img[src*="stale_b"]')).toHaveLength(0)

    // 新 KEPT 请求返回后，只渲染 KEPT 的图
    inflight[1].resolve({
      items: [makeImage('kept_a', true)],
      total: 1,
      page: 1,
      page_size: 40,
      has_next: false,
    })
    await waitFor(() => expect(cards(container)).toHaveLength(1))
    expect(container.querySelectorAll('img[src*="stale_a"]')).toHaveLength(0)
    expect(container.querySelector('img[src*="kept_a"]')).toBeTruthy()
  })
})
