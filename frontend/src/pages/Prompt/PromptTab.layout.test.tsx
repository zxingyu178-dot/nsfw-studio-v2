import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { PromptDTO, PromptImageDTO } from '../../types/workbench'
import { PromptTab } from './PromptTab'

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
    created_at: '2026-10-22T00:00:00Z',
    thumbnail_url: `/api/v1/images/${id}/thumbnail`,
    preview_url: `/api/v1/images/${id}/preview`,
  }
}

function makePrompt(): PromptDTO {
  return {
    id: 'prm_layout',
    name: '整行 Prompt',
    favorite: false,
    archived: false,
    preview_image_id: null,
    created_at: '2026-10-21T00:00:00Z',
    updated_at: '2026-10-22T00:00:00Z',
    current_version: {
      id: 'prmv_layout',
      prompt_id: 'prm_layout',
      version_no: 1,
      mode: 'full',
      positive_prompt: 'cinematic portrait, detailed lighting',
      negative_prompt: 'blur',
      structured: { style: '', face: '', clothing: '', pose: '', scene: '', composition: '', lighting: '', extra: '' },
      created_at: '2026-10-21T00:00:00Z',
    },
    images: [makeImage('img_1'), makeImage('img_2')],
    images_total: 2,
  }
}

function listResponse(items: PromptDTO[]) {
  return { items, total: items.length, limit: 50, offset: 0 }
}

function renderTab() {
  return render(
    <MemoryRouter>
      <PromptTab />
    </MemoryRouter>,
  )
}

describe('Prompt 整行布局、软删除与加载骨架', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('在单列列表卡片中渲染更大的生成图缩略行，并启用异步懒加载', async () => {
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list).mockResolvedValue(listResponse([makePrompt()]) as never)
    const { container } = renderTab()

    await screen.findByText('整行 Prompt')
    expect(container.querySelector('.pp-grid--single > .pp-card')).toBeTruthy()
    const gallery = screen.getByLabelText('该提示词生成过的图片，共 2 张')
    expect(gallery.querySelectorAll('.pp-card__gallery-thumb')).toHaveLength(2)
    gallery.querySelectorAll('img').forEach((image) => {
      expect(image.getAttribute('loading')).toBe('lazy')
      expect(image.getAttribute('decoding')).toBe('async')
    })
  })

  it('确认删除后调用 archive，刷新列表并显示软删除提示', async () => {
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list)
      .mockResolvedValueOnce(listResponse([makePrompt()]) as never)
      .mockResolvedValue(listResponse([]) as never)
    vi.mocked(promptApi.archive).mockResolvedValue(undefined as never)
    renderTab()

    await screen.findByText('整行 Prompt')
    fireEvent.click(screen.getByRole('button', { name: '删除' }))
    expect(screen.getByText('软删除后，可在“显示已归档”中找回。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))

    await waitFor(() => expect(promptApi.archive).toHaveBeenCalledWith('prm_layout'))
    expect(await screen.findByText('已软删除 Prompt，可在“显示已归档”中找回')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByText('整行 Prompt')).toBeNull())
  })

  it('取消删除不调用 archive', async () => {
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list).mockResolvedValue(listResponse([makePrompt()]) as never)
    renderTab()

    await screen.findByText('整行 Prompt')
    fireEvent.click(screen.getByRole('button', { name: '删除' }))
    fireEvent.click(screen.getByRole('button', { name: '取消' }))

    expect(promptApi.archive).not.toHaveBeenCalled()
    expect(screen.queryByText('软删除后，可在“显示已归档”中找回。')).toBeNull()
  })

  it('初始加载中显示整行骨架，不显示裸加载文案', async () => {
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list).mockReturnValue(new Promise(() => {}) as never)
    const { container } = renderTab()

    expect(container.querySelectorAll('.pp-skeleton')).toHaveLength(3)
    expect(screen.queryByText('加载中…')).toBeNull()
  })
})
