import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { imageApi, jobApi } from '../../api/client'
import GalleryPage from './GalleryPage'
import type { ImageDTO } from '../../types/workbench'

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

function makeImage(id: string): ImageDTO {
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
    review_status: 'REJECTED',
    favorite: false,
    status: 'REJECT',
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
  vi.mocked(imageApi.list).mockResolvedValue({
    items: [makeImage('img_a'), makeImage('img_b')],
    total: 2,
    page: 1,
    page_size: 40,
    has_next: false,
  } as never)
  vi.mocked(imageApi.stats).mockResolvedValue({
    total: 0, new: 0, keep: 0, reject: 0, archived: 0, favorites: 0,
  } as never)
  vi.mocked(imageApi.versions).mockRejectedValue(new Error('none'))
  vi.mocked(imageApi.provenance).mockRejectedValue(new Error('none'))
  vi.mocked(imageApi.jobGroups).mockResolvedValue({
    items: [], total: 0, page: 1, page_size: 20, has_next: false,
  } as never)
  vi.mocked(jobApi.list).mockResolvedValue({ items: [] } as never)
})

describe('Gallery 淘汰图删除入口', () => {
  it('工具栏显式“删除淘汰图”按钮打开全局清理预览', async () => {
    vi.mocked(imageApi.cleanupRejected).mockResolvedValue({
      candidate_count: 2,
      deletable_count: 2,
      protected_count: 0,
      total_bytes: 2048,
      protected_items: [],
    } as never)

    renderPage()
    await screen.findByText('共 2 张')
    fireEvent.click(screen.getByRole('button', { name: '删除淘汰图' }))

    await screen.findByText('实际可删')
    expect(imageApi.cleanupRejected).toHaveBeenCalledWith({ confirm: false })
  })

  it('多选删除使用相同 ids 预览和确认，完成后刷新并退出选择', async () => {
    const selectedIds = ['img_a', 'img_b']
    vi.mocked(imageApi.cleanupRejected)
      .mockResolvedValueOnce({
        candidate_count: 2,
        deletable_count: 2,
        protected_count: 0,
        total_bytes: 2048,
        protected_items: [],
      } as never)
      .mockResolvedValueOnce({
        candidate_count: 2,
        deletable_count: 2,
        protected_count: 0,
        total_bytes: 2048,
        protected_items: [],
        deleted_count: 2,
        deleted_bytes: 2048,
      } as never)

    const { container } = renderPage()
    await screen.findByText('共 2 张')
    const initialListCalls = vi.mocked(imageApi.list).mock.calls.length

    fireEvent.click(screen.getByRole('button', { name: '选择' }))
    container.querySelectorAll('.gal-card').forEach((card) => fireEvent.click(card))
    expect(screen.getByText('已选 2 张')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '删除' }))
    await waitFor(() => expect(imageApi.cleanupRejected).toHaveBeenNthCalledWith(1, {
      image_ids: selectedIds,
      confirm: false,
    }))
    expect(screen.getByText('实际可删')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '确认删除 2 张' }))

    await waitFor(() => expect(imageApi.cleanupRejected).toHaveBeenNthCalledWith(2, {
      image_ids: selectedIds,
      confirm: true,
    }))
    await waitFor(() => expect(vi.mocked(imageApi.list).mock.calls.length).toBeGreaterThan(initialListCalls))
    expect(imageApi.stats).toHaveBeenCalled()
    expect(screen.queryByText('已选 2 张')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('已删除 2 张')
  })

  it('多选预览可删 0 张时禁用确认按钮', async () => {
    vi.mocked(imageApi.cleanupRejected).mockResolvedValue({
      candidate_count: 2,
      deletable_count: 0,
      protected_count: 2,
      total_bytes: 0,
      protected_items: [{ image_id: 'img_a', reasons: ['被素材引用'] }],
    } as never)

    const { container } = renderPage()
    await screen.findByText('共 2 张')
    fireEvent.click(screen.getByRole('button', { name: '选择' }))
    fireEvent.click(container.querySelector('.gal-card') as HTMLElement)
    fireEvent.click(screen.getByRole('button', { name: '删除' }))

    expect(await screen.findByRole('button', { name: '确认删除 0 张' })).toBeDisabled()
  })
})
