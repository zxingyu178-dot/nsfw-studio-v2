import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PromptTab } from './PromptTab'
import type { PromptDTO, PromptImageDTO } from '../../types/workbench'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {},
  promptApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    addVersion: vi.fn(),
    updateMeta: vi.fn(),
    archive: vi.fn(),
    restore: vi.fn(),
    listVersions: vi.fn(),
    restoreVersion: vi.fn(),
    setPreviewImage: vi.fn(),
    clearPreviewImage: vi.fn(),
  },
  imageApi: { list: vi.fn(), get: vi.fn() },
}))

function makeImage(id: string): PromptImageDTO {
  return {
    id,
    job_id: 'job_1',
    job_status: 'COMPLETED',
    module_id: 'basic_generate',
    width: 1024,
    height: 1024,
    created_at: '2026-10-20T00:00:00Z',
    thumbnail_url: `/api/v1/images/${id}/thumbnail`,
    preview_url: `/api/v1/images/${id}/preview`,
  }
}

function makePrompt(overrides: Partial<PromptDTO> = {}): PromptDTO {
  return {
    id: 'prm_1',
    name: '测试 Prompt',
    favorite: false,
    archived: false,
    preview_image_id: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    current_version: {
      id: 'prmv_1',
      prompt_id: 'prm_1',
      version_no: 1,
      mode: 'full',
      positive_prompt: 'masterpiece, 1girl, night city',
      negative_prompt: 'blur',
      structured: { style: '', face: '', clothing: '', pose: '', scene: '', composition: '', lighting: '', extra: '' },
      created_at: '2026-01-01T00:00:00Z',
    },
    ...overrides,
  }
}

async function mockList(prompts: PromptDTO[]) {
  const { promptApi } = await import('../../api/client')
  vi.mocked(promptApi.list).mockResolvedValue({
    items: prompts,
    total: prompts.length,
    limit: 50,
    offset: 0,
  } as never)
}

function renderTab() {
  return render(
    <MemoryRouter>
      <PromptTab />
    </MemoryRouter>,
  )
}

describe('Prompt 卡片：提示词 → 生成图（Phase 0.17.2）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('请求列表时带上 include_images 与 images_limit', async () => {
    await mockList([makePrompt()])
    const { promptApi } = await import('../../api/client')
    renderTab()
    await waitFor(() => expect(promptApi.list).toHaveBeenCalled())
    expect(vi.mocked(promptApi.list).mock.calls[0][0]).toMatchObject({
      include_images: true,
      images_limit: 3,
    })
  })

  it('卡片下渲染生成图缩略行，并显示还有多少张未展示', async () => {
    await mockList([
      makePrompt({
        images: [makeImage('img_1'), makeImage('img_2'), makeImage('img_3')],
        images_total: 5,
      }),
    ])
    renderTab()

    const gallery = await screen.findByLabelText('该提示词生成过的图片，共 5 张')
    const thumbs = gallery.querySelectorAll('.pp-card__gallery-thumb')
    expect(thumbs.length).toBe(3)
    expect(gallery.textContent).toContain('+2')
    expect(gallery.querySelector('img')?.getAttribute('src')).toBe('/api/v1/images/img_1/thumbnail')
  })

  it('没有生成图时不渲染缩略行', async () => {
    await mockList([makePrompt()])
    renderTab()
    await screen.findByText('测试 Prompt')
    expect(document.querySelector('.pp-card__gallery')).toBeNull()
  })

  it('点击缩略图打开预览大图（preview_url）', async () => {
    await mockList([makePrompt({ images: [makeImage('img_1')], images_total: 1 })])
    renderTab()

    const thumb = await screen.findByRole('button', { name: '查看生成图 img_1' })
    fireEvent.click(thumb)

    await waitFor(() => {
      const modalImg = document.querySelector('.pp-card__preview-modal') as HTMLImageElement | null
      expect(modalImg?.getAttribute('src')).toBe('/api/v1/images/img_1/preview')
    })
  })
})
