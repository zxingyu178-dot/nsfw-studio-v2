import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { imageApi, jobApi } from '../../api/client'
import GalleryPage from './GalleryPage'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {},
  imageApi: {
    list: vi.fn(),
    ids: vi.fn(),
    stats: vi.fn(),
    versions: vi.fn(),
    provenance: vi.fn(),
    review: vi.fn(),
    favorite: vi.fn(),
    setStatus: vi.fn(),
    upscale: vi.fn(),
    workbench: vi.fn(),
    importFiles: vi.fn(),
    batchStatus: vi.fn(),
    jobSummary: vi.fn(),
    jobGroups: vi.fn(),
    cleanupRejected: vi.fn(),
  },
  jobApi: { list: vi.fn(), get: vi.fn() },
  assetApi: { create: vi.fn() },
  promptApi: { list: vi.fn(), setPreviewImage: vi.fn() },
}))

function renderPage(initialEntry = '/gallery') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <GalleryPage />
    </MemoryRouter>,
  )
}

async function selectCurrentFilter(): Promise<void> {
  fireEvent.click(screen.getByRole('button', { name: '选择' }))
  fireEvent.click(screen.getByRole('button', { name: '全选当前筛选' }))
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(imageApi.list).mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 40,
    has_next: false,
  } as never)
  vi.mocked(imageApi.versions).mockRejectedValue(new Error('none'))
  vi.mocked(imageApi.provenance).mockRejectedValue(new Error('none'))
  vi.mocked(imageApi.jobGroups).mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
    has_next: false,
  } as never)
  vi.mocked(jobApi.list).mockResolvedValue({ items: [] } as never)
})

describe('Gallery 全选当前筛选与分块批量操作', () => {
  it('全选 1200 张后确认归档，并按 500/500/200 顺序提交', async () => {
    const ids = Array.from({ length: 1200 }, (_, index) => `img_${index}`)
    vi.mocked(imageApi.ids).mockResolvedValue({ ids, total: 1200, truncated: false, limit: 10000 })
    vi.mocked(imageApi.batchStatus).mockImplementation(async ({ image_ids }) => ({
      updated: image_ids.length,
      items: [],
    }))
    renderPage()

    await selectCurrentFilter()
    expect(await screen.findByText('已选 1200 张')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '归档' }))
    expect(screen.getByText('确认归档 1200 张图片？')).toBeInTheDocument()
    expect(imageApi.batchStatus).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: '确认归档' }))

    await waitFor(() => expect(imageApi.batchStatus).toHaveBeenCalledTimes(3))
    expect(imageApi.batchStatus).toHaveBeenNthCalledWith(1, {
      image_ids: ids.slice(0, 500),
      status: 'ARCHIVED',
    })
    expect(imageApi.batchStatus).toHaveBeenNthCalledWith(2, {
      image_ids: ids.slice(500, 1000),
      status: 'ARCHIVED',
    })
    expect(imageApi.batchStatus).toHaveBeenNthCalledWith(3, {
      image_ids: ids.slice(1000),
      status: 'ARCHIVED',
    })
    expect(await screen.findByRole('status')).toHaveTextContent('已归档 1200 张')
  })

  it('ids 结果被截断时提示仅选中返回的前 N 张', async () => {
    const ids = Array.from({ length: 1000 }, (_, index) => `img_${index}`)
    vi.mocked(imageApi.ids).mockResolvedValue({ ids, total: 1200, truncated: true, limit: 1000 })
    renderPage()

    await selectCurrentFilter()

    expect(await screen.findByText('已选 1000 张')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('仅选中前 1000 张')
  })

  it('全选接口使用当前列表筛选但不携带分页参数', async () => {
    vi.mocked(imageApi.ids).mockResolvedValue({ ids: [], total: 0, truncated: false, limit: 10000 })
    renderPage('/gallery?job=job_1&source=import')

    fireEvent.click(screen.getByRole('tab', { name: '归档' }))
    await selectCurrentFilter()

    await waitFor(() => expect(imageApi.ids).toHaveBeenCalledWith({
      job_id: 'job_1',
      sort: 'created_desc',
      status: 'ARCHIVED',
      source: 'import',
    }))
  })

  it('淘汰 100 张时不弹确认并直接提交', async () => {
    const ids = Array.from({ length: 100 }, (_, index) => `img_${index}`)
    vi.mocked(imageApi.ids).mockResolvedValue({ ids, total: 100, truncated: false, limit: 10000 })
    vi.mocked(imageApi.batchStatus).mockResolvedValue({ updated: 100, items: [] } as never)
    renderPage()

    await selectCurrentFilter()
    expect(await screen.findByText('已选 100 张')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '淘汰' }))

    await waitFor(() => expect(imageApi.batchStatus).toHaveBeenCalledTimes(1))
    expect(screen.queryByText('确认淘汰 100 张图片？')).not.toBeInTheDocument()
  })

  it('分块失败后停止，并保留选择且显示已成功数量与错误', async () => {
    const ids = Array.from({ length: 600 }, (_, index) => `img_${index}`)
    vi.mocked(imageApi.ids).mockResolvedValue({ ids, total: 600, truncated: false, limit: 10000 })
    vi.mocked(imageApi.batchStatus)
      .mockResolvedValueOnce({ updated: 500, items: [] } as never)
      .mockRejectedValueOnce(new Error('第二块失败'))
    renderPage()

    await selectCurrentFilter()
    expect(await screen.findByText('已选 600 张')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '归档' }))
    fireEvent.click(screen.getByRole('button', { name: '确认归档' }))

    await waitFor(() => expect(imageApi.batchStatus).toHaveBeenCalledTimes(2))
    expect(await screen.findByText(/已成功 500\/600 张；第二块失败/)).toBeInTheDocument()
    expect(screen.getByText('已选 600 张')).toBeInTheDocument()
  })
})
