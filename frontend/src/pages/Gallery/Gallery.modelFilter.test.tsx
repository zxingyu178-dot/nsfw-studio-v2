import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { imageApi, jobApi, promptApi } from '../../api/client'
import GalleryPage from './GalleryPage'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {},
  imageApi: {
    list: vi.fn(),
    stats: vi.fn(),
    series: vi.fn(),
    models: vi.fn(),
    versions: vi.fn(),
    provenance: vi.fn(),
    review: vi.fn(),
    favorite: vi.fn(),
    setStatus: vi.fn(),
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

const MODEL = 'NoobAI-XL-v1.1.safetensors'

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(imageApi.list).mockResolvedValue({
    items: [], total: 0, page: 1, page_size: 40, has_next: false,
  } as never)
  vi.mocked(imageApi.stats).mockResolvedValue({
    total: 0, new: 0, keep: 0, reject: 0, archived: 0, favorites: 0,
  } as never)
  vi.mocked(imageApi.series).mockResolvedValue({ items: [] } as never)
  vi.mocked(imageApi.models).mockResolvedValue({
    items: [{ model: MODEL, count: 3 }],
  } as never)
  vi.mocked(imageApi.versions).mockRejectedValue(new Error('none'))
  vi.mocked(imageApi.provenance).mockRejectedValue(new Error('none'))
  vi.mocked(jobApi.list).mockResolvedValue({ items: [] } as never)
  vi.mocked(jobApi.get).mockResolvedValue({} as never)
  vi.mocked(promptApi.list).mockResolvedValue({ items: [] } as never)
})

function renderPage(entry = '/gallery') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <GalleryPage />
    </MemoryRouter>,
  )
}

describe('图库底模筛选', () => {
  it('下拉展示任务快照底模与张数，选择后列表与统计带上 model', async () => {
    renderPage()

    const select = await screen.findByLabelText('底模')
    expect(await screen.findByRole('option', { name: 'NoobAI-XL-v1.1（3）' })).toBeInTheDocument()

    fireEvent.change(select, { target: { value: MODEL } })

    await waitFor(() => expect(imageApi.list).toHaveBeenCalledWith(
      expect.objectContaining({ model: MODEL }),
    ))
    expect(select).toHaveValue(MODEL)
  })

  it('URL 带 model 时首屏即按底模过滤', async () => {
    renderPage(`/gallery?model=${encodeURIComponent(MODEL)}`)

    await waitFor(() => expect(imageApi.list).toHaveBeenCalledWith(
      expect.objectContaining({ model: MODEL }),
    ))
    expect(await screen.findByLabelText('底模')).toHaveValue(MODEL)
  })

  it('未记录底模选项以 __none__ 传递', async () => {
    renderPage()

    const select = await screen.findByLabelText('底模')
    fireEvent.change(select, { target: { value: '__none__' } })

    await waitFor(() => expect(imageApi.list).toHaveBeenCalledWith(
      expect.objectContaining({ model: '__none__' }),
    ))
  })
})
