import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { imageApi, jobApi } from '../../../api/client'
import type { ImageDTO } from '../../../types/workbench'
import { GalleryDetailDrawer, type GalleryDetailDrawerProps } from './GalleryDetailDrawer'

vi.mock('../../../api/client', () => ({
  ApiRequestError: class extends Error {},
  imageApi: {
    versions: vi.fn(),
    provenance: vi.fn(),
    setStatus: vi.fn(),
    favorite: vi.fn(),
    workbench: vi.fn(),
    cleanupRejected: vi.fn(),
  },
  jobApi: { get: vi.fn() },
  assetApi: { create: vi.fn() },
  promptApi: { list: vi.fn(), setPreviewImage: vi.fn() },
}))

const image: ImageDTO = {
  id: 'img_layout',
  job_id: 'job_layout',
  job_item_id: 'item_layout',
  parent_image_id: null,
  kind: 'original',
  file_path: 'images/layout.png',
  width: 1024,
  height: 768,
  seed: 777,
  review_status: 'UNREVIEWED',
  favorite: false,
  source: 'comfyui',
  metadata: {},
  created_at: '2026-10-20T08:00:00Z',
  updated_at: '2026-10-20T08:00:00Z',
}

function renderDrawer(props: Partial<GalleryDetailDrawerProps> = {}) {
  return render(
    <MemoryRouter>
      <GalleryDetailDrawer
        image={image}
        onClose={vi.fn()}
        onUpdated={vi.fn()}
        onSelectImage={vi.fn()}
        onUseAsInput={vi.fn()}
        onReviewStart={vi.fn()}
        onFavoriteStart={vi.fn()}
        onPreviewLightbox={vi.fn()}
        onDeleted={vi.fn()}
        {...props}
      />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(jobApi.get).mockResolvedValue({
    id: 'job_layout',
    positive_prompt_snapshot: 'layout prompt',
    negative_prompt_snapshot: 'layout negative',
  } as never)
  vi.mocked(imageApi.versions).mockResolvedValue({
    image,
    parent: null,
    children: [{ ...image, id: 'img_layout_child', kind: 'upscaled', width: 2048, height: 1536 }],
  })
  vi.mocked(imageApi.provenance).mockResolvedValue({
    image_id: image.id,
    kind: image.kind,
    parent_image_id: null,
    root_image_id: image.id,
    scale: null,
    job_id: image.job_id,
    job_item_id: image.job_item_id,
    stage_id: 'stage_layout',
    stage_index: 0,
    stage_item_id: 'stage_item_layout',
    module_id: 'basic_generate',
    module_version: '1.0.0',
    provider: 'comfyui',
    binding_version: 'v1',
    workflow_hash: 'workflow-layout',
    binding_hash: 'binding-layout',
    seed: 777,
  })
})

describe('GalleryDetailDrawer 布局契约', () => {
  it('按概览、操作、版本、高级信息和危险区分区，并保留核心参数与危险操作语义', async () => {
    renderDrawer()

    await screen.findByText('workflow-layout')
    expect.soft(screen.queryByRole('heading', { name: '概览' })).toBeInTheDocument()
    expect.soft(screen.queryByRole('heading', { name: '操作' })).toBeInTheDocument()
    expect.soft(screen.queryByRole('heading', { name: '版本' })).toBeInTheDocument()
    expect.soft(screen.queryByRole('heading', { name: '高级信息' })).toBeInTheDocument()
    expect.soft(screen.queryByRole('heading', { name: '危险区' })).toBeInTheDocument()

    expect(screen.getByText('1024 × 768')).toBeInTheDocument()
    expect(screen.getAllByText('777').length).toBeGreaterThan(0)

    const rejectButton = screen.getByRole('button', { name: '淘汰此图' })
    expect(rejectButton).toBeInTheDocument()
    expect(rejectButton).toHaveClass('ds-btn--danger')
  })

  it('概览显示原任务底模短名，缺少快照时显示占位', async () => {
    vi.mocked(jobApi.get).mockResolvedValue({
      id: 'job_layout',
      positive_prompt_snapshot: 'layout prompt',
      negative_prompt_snapshot: '',
      workflow_snapshot: {
        modules: [{ module_id: 'anime_generate', config: { model: 'NoobAI-XL-v1.1.safetensors' } }],
      },
    } as never)
    renderDrawer()
    expect(await screen.findByText('底模')).toBeInTheDocument()
    expect(await screen.findByText('NoobAI-XL-v1.1')).toBeInTheDocument()
  })

  it('底模旁可一键只看此底模，并向筛选传递原始文件名', async () => {
    vi.mocked(jobApi.get).mockResolvedValue({
      id: 'job_layout',
      positive_prompt_snapshot: 'layout prompt',
      negative_prompt_snapshot: '',
      workflow_snapshot: {
        modules: [{ module_id: 'anime_generate', config: { model: ' NoobAI-XL-v1.1.safetensors ' } }],
      },
    } as never)
    const onFilterModel = vi.fn()
    renderDrawer({ onFilterModel })
    fireEvent.click(await screen.findByRole('button', { name: '只看此底模' }))
    expect(onFilterModel).toHaveBeenCalledWith('NoobAI-XL-v1.1.safetensors')
  })
})
