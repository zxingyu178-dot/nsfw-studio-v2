import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
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
    jobGroups: vi.fn(),
  },
  jobApi: { list: vi.fn(), get: vi.fn() },
  assetApi: { create: vi.fn() },
}))

function LocationProbe() {
  const location = useLocation()
  const navigate = useNavigate()
  return (
    <div>
      <output aria-label="当前查询参数">{location.search}</output>
      <button type="button" onClick={() => navigate(-1)}>后退</button>
      <button type="button" onClick={() => navigate(1)}>前进</button>
    </div>
  )
}

function renderPage(initialEntry = '/gallery') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <GalleryPage />
      <LocationProbe />
    </MemoryRouter>,
  )
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

describe('Gallery 来源筛选', () => {
  it('从 URL 恢复 V1 导入筛选，并在选择生成后同步 URL 与第一页查询', async () => {
    renderPage('/gallery?job=job_1&source=import')

    const sourceSelect = screen.getByRole('combobox', { name: '来源' })
    expect(sourceSelect).toHaveValue('import')
    await waitFor(() =>
      expect(imageApi.list).toHaveBeenCalledWith(
        expect.objectContaining({ job_id: 'job_1', source: 'import', page: 1 }),
      ),
    )

    fireEvent.change(sourceSelect, { target: { value: 'comfyui' } })

    await waitFor(() => {
      expect(screen.getByLabelText('当前查询参数')).toHaveTextContent('?job=job_1&source=comfyui')
      expect(imageApi.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ job_id: 'job_1', source: 'comfyui', page: 1 }),
      )
    })

    fireEvent.click(screen.getByRole('button', { name: '后退' }))
    await waitFor(() => {
      expect(sourceSelect).toHaveValue('import')
      expect(imageApi.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ job_id: 'job_1', source: 'import', page: 1 }),
      )
    })

    fireEvent.click(screen.getByRole('button', { name: '前进' }))
    await waitFor(() => expect(sourceSelect).toHaveValue('comfyui'))

    fireEvent.change(sourceSelect, { target: { value: '' } })
    await waitFor(() => {
      expect(screen.getByLabelText('当前查询参数')).toHaveTextContent('?job=job_1')
      expect(imageApi.list).toHaveBeenLastCalledWith(
        expect.not.objectContaining({ source: expect.anything() }),
      )
    })
  })

  it('非法 source 静默回退全部并从 URL 移除', async () => {
    renderPage('/gallery?source=mock')

    expect(screen.getByRole('combobox', { name: '来源' })).toHaveValue('')
    await waitFor(() => expect(screen.getByLabelText('当前查询参数')).toHaveTextContent(''))
    expect(imageApi.list).toHaveBeenCalledWith(expect.not.objectContaining({ source: expect.anything() }))
  })
})
