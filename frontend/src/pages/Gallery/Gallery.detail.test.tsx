import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { imageApi, jobApi, promptApi } from '../../api/client'
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
    setStatus: vi.fn(),
    cleanupRejected: vi.fn(),
  },
  jobApi: { list: vi.fn(), get: vi.fn() },
  assetApi: { create: vi.fn() },
  promptApi: { list: vi.fn(), setPreviewImage: vi.fn() },
}))

const image = {
  id: 'img_detail',
  job_id: 'job_x',
  kind: 'original',
  source: 'comfyui',
  review_status: 'UNREVIEWED',
  favorite: false,
  seed: 777,
  width: 1024,
  height: 768,
  created_at: '2026-02-03T04:05:00',
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
  vi.mocked(imageApi.list).mockResolvedValue({ items: [image], total: 1, page: 1, page_size: 40, has_next: false } as never)
  vi.mocked(imageApi.versions).mockRejectedValue(new Error('none'))
  vi.mocked(imageApi.provenance).mockRejectedValue(new Error('none'))
  vi.mocked(jobApi.list).mockResolvedValue({ items: [] } as never)
  vi.mocked(jobApi.get).mockResolvedValue({
    id: 'job_x',
    positive_prompt_snapshot: 'a beautiful cat, masterpiece',
    negative_prompt_snapshot: 'blur',
  } as never)
  vi.mocked(promptApi.list).mockResolvedValue({
    items: [{ id: 'prm_9', name: '猫娘模板' }],
  } as never)
  vi.mocked(promptApi.setPreviewImage).mockResolvedValue({} as never)
})

describe('ImageDetail 详情信息栏与操作', () => {
  it('展示尺寸/Seed/时间/Prompt，并有复制与删除入口', async () => {
    const { container } = renderPage()
    await screen.findByText('共 1 张')
    fireEvent.click(container.querySelector('.gal-card') as HTMLElement)

    expect(await screen.findByText('图片详情')).toBeInTheDocument()
    // 信息栏字段
    expect(screen.getByText('1024 × 768')).toBeInTheDocument()
    expect(screen.getByText('777')).toBeInTheDocument()
    expect(screen.getByText('a beautiful cat, masterpiece')).toBeInTheDocument()
    // 操作入口
    expect(screen.getByRole('button', { name: '复制 Prompt' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '删除此图片' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '选择 Prompt' })).toBeInTheDocument()
  })

  it('「设为 Prompt 封面」选择 Prompt 后调用 setPreviewImage', async () => {
    const { container } = renderPage()
    await screen.findByText('共 1 张')
    fireEvent.click(container.querySelector('.gal-card') as HTMLElement)
    await screen.findByText('图片详情')

    fireEvent.click(screen.getByRole('button', { name: '选择 Prompt' }))
    // Prompt 列表加载后出现选择下拉与「设为封面」
    await screen.findByRole('button', { name: '设为封面' })
    const selects = container.querySelectorAll('.ds-drawer select')
    fireEvent.change(selects[selects.length - 1], { target: { value: 'prm_9' } })
    fireEvent.click(screen.getByRole('button', { name: '设为封面' }))

    await waitFor(() =>
      expect(promptApi.setPreviewImage).toHaveBeenCalledWith('prm_9', 'img_detail'),
    )
  })

  it('删除时被引用保护则禁止删除并提示', async () => {
    vi.mocked(imageApi.cleanupRejected).mockResolvedValue({
      candidate_count: 1,
      total_bytes: 1234,
      protected_count: 1,
    } as never)
    const { container } = renderPage()
    await screen.findByText('共 1 张')
    fireEvent.click(container.querySelector('.gal-card') as HTMLElement)
    await screen.findByText('图片详情')

    fireEvent.click(screen.getByRole('button', { name: '删除此图片' }))
    fireEvent.click(screen.getByRole('button', { name: /确认删除/ }))

    expect(await screen.findByText(/禁止删除/)).toBeInTheDocument()
    expect(imageApi.cleanupRejected).not.toHaveBeenCalledWith(expect.objectContaining({ confirm: true }))
  })
})
