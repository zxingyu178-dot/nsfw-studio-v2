import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useNavigate } from 'react-router-dom'
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
    workbench: vi.fn(),
    importFiles: vi.fn(),
    batchStatus: vi.fn(),
    jobSummary: vi.fn(),
    jobGroups: vi.fn(),
  },
  reviewSessionApi: {
    latestSession: vi.fn(),
    createSession: vi.fn(),
    queuePage: vi.fn(),
    newCount: vi.fn(),
  },
  jobApi: { list: vi.fn(), get: vi.fn() },
  assetApi: { create: vi.fn() },
}))

function BackButton() {
  const navigate = useNavigate()
  return <button type="button" onClick={() => navigate(-1)}>后退</button>
}

function renderPage(initialEntry = '/gallery') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <BackButton />
      <GalleryPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(imageApi.list).mockResolvedValue({
    items: [], total: 0, page: 1, page_size: 40, has_next: false,
  } as never)
  vi.mocked(imageApi.versions).mockRejectedValue(new Error('none'))
  vi.mocked(imageApi.provenance).mockRejectedValue(new Error('none'))
  vi.mocked(imageApi.jobGroups).mockResolvedValue({
    items: [], total: 0, page: 1, page_size: 20, has_next: false,
  } as never)
  vi.mocked(jobApi.list).mockResolvedValue({ items: [] } as never)
})

describe('Gallery 设计融合', () => {
  it('渲染图库工作区标题、状态侧栏和顶部审核入口', () => {
    const { container } = renderPage()

    expect(screen.getByRole('heading', { name: '图库' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: '图库分类' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '审核' })).toBeInTheDocument()
    expect(container.querySelector('.gal-workspace__sidebar')).toBeInTheDocument()
    expect(container.querySelector('.gal-workspace__canvas')).toBeInTheDocument()
  })

  it.each([
    ['NEW', { status: 'NEW' }],
    ['REJECT', { status: 'REJECT' }],
  ])('从 status=%s 深链恢复筛选', async (status, expected) => {
    renderPage(`/gallery?status=${status}`)

    await waitFor(() => {
      expect(imageApi.list).toHaveBeenLastCalledWith(expect.objectContaining(expected))
    })
  })

  it('review=1 只打开现有冻结审核入口', async () => {
    const api = await import('../../api/client')
    vi.mocked(api.reviewSessionApi.latestSession).mockResolvedValue({
      id: 'review_1', status: 'COMPLETED', current_index: 0,
    } as never)

    renderPage('/gallery?status=NEW&review=1')

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(api.reviewSessionApi.latestSession).toHaveBeenCalledTimes(1)
    expect(api.reviewSessionApi.createSession).not.toHaveBeenCalled()
  })

  it('筛选来自 URL，返回时恢复全部图片', async () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: /^废片/ }))
    await waitFor(() => {
      expect(imageApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'REJECT' }))
    })
    fireEvent.click(screen.getByRole('button', { name: '后退' }))
    await waitFor(() => {
      expect(vi.mocked(imageApi.list).mock.lastCall?.[0]?.status).toBeUndefined()
    })
  })
})
