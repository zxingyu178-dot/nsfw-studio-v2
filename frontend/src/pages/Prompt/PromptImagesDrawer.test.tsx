import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PromptImagesDrawer } from './PromptImagesDrawer'
import { PromptTab } from './PromptTab'
import type { PromptDTO, PromptImageDTO } from '../../types/workbench'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {},
  promptApi: {
    list: vi.fn(),
    listImages: vi.fn(),
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
    createEvaluation: vi.fn(),
    setStatus: vi.fn(),
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

/** 服务端分页 mock：offset/limit 真正切分，便于验证 100 张全部可达。 */
async function mockImages(total: number) {
  const { promptApi } = await import('../../api/client')
  const all = Array.from({ length: total }, (_, i) => makeImage(`img_${i + 1}`))
  vi.mocked(promptApi.listImages).mockImplementation(async (_id, params = {}) => {
    const offset = params.offset ?? 0
    const limit = params.limit ?? 40
    return {
      items: all.slice(offset, offset + limit),
      total,
      limit,
      offset,
    } as never
  })
  return all
}

function renderDrawer(promptId: string, onClose = vi.fn()) {
  render(<PromptImagesDrawer promptId={promptId} promptName="测试 Prompt" onClose={onClose} />)
  return onClose
}

describe('Prompt 全部关联图片抽屉（v0.37 P1-A）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('0 张：显示明确空态，不显示加载更多', async () => {
    await mockImages(0)
    renderDrawer('prm_empty')
    expect(await screen.findByText('该 Prompt 暂无关联图片。')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '加载更多' })).toBeNull()
  })

  it('1 张：显示 1 个缩略图与总数', async () => {
    await mockImages(1)
    renderDrawer('prm_one')
    await screen.findByText('已加载 1 / 共 1 张')
    expect(document.querySelectorAll('.pp-imgdrawer__thumb').length).toBe(1)
  })

  it('3 / 4 张：全部直接加载，无分页按钮', async () => {
    await mockImages(3)
    renderDrawer('prm_three')
    await screen.findByText('已加载 3 / 共 3 张')
    expect(screen.queryByRole('button', { name: '加载更多' })).toBeNull()

    await mockImages(4)
    renderDrawer('prm_four')
    await screen.findByText('已加载 4 / 共 4 张')
    expect(screen.queryByRole('button', { name: '加载更多' })).toBeNull()
  })

  it('50 张：首屏 40，再加载一次到达 50', async () => {
    await mockImages(50)
    renderDrawer('prm_fifty')
    await screen.findByText('已加载 40 / 共 50 张')
    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    await screen.findByText('已加载 50 / 共 50 张')
    expect(screen.queryByRole('button', { name: '加载更多' })).toBeNull()
  })

  it('100 张：分三页全部可达，点击缩略图可放大', async () => {
    const { promptApi } = await import('../../api/client')
    await mockImages(100)
    renderDrawer('prm_hundred')
    await screen.findByText('已加载 40 / 共 100 张')

    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    await screen.findByText('已加载 80 / 共 100 张')
    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    await screen.findByText('已加载 100 / 共 100 张')

    expect(document.querySelectorAll('.pp-imgdrawer__thumb').length).toBe(100)
    const offsets = vi.mocked(promptApi.listImages).mock.calls.map((call) => call[1]?.offset)
    expect(offsets).toEqual([0, 40, 80])

    const lastThumb = document.querySelectorAll('.pp-imgdrawer__thumb')[99] as HTMLButtonElement
    fireEvent.click(lastThumb)
    await waitFor(() => {
      const preview = document.querySelector('.pp-imgdrawer__preview img') as HTMLImageElement | null
      expect(preview?.getAttribute('src')).toBe('/api/v1/images/img_100/preview')
    })
  })

  it('关闭重开同一筛选复用已加载分页，不重新拉取', async () => {
    const { promptApi } = await import('../../api/client')
    await mockImages(50)
    const first = render(<PromptImagesDrawer promptId="prm_cache" promptName="测试 Prompt" onClose={vi.fn()} />)
    await screen.findByText('已加载 40 / 共 50 张')
    expect(promptApi.listImages).toHaveBeenCalledTimes(1)
    first.unmount()

    render(<PromptImagesDrawer promptId="prm_cache" promptName="测试 Prompt" onClose={vi.fn()} />)
    await screen.findByText('已加载 40 / 共 50 张')
    expect(promptApi.listImages).toHaveBeenCalledTimes(1)
  })
})

describe('Prompt 卡片 +N 打开全部图片（v0.37 P1-A）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('100 张图只预览 3 张，+97 可点击并展示全部', async () => {
    const { promptApi } = await import('../../api/client')
    const images = [makeImage('img_1'), makeImage('img_2'), makeImage('img_3')]
    vi.mocked(promptApi.list).mockResolvedValue({
      items: [makePrompt({ id: 'prm_card', images, images_total: 100 })],
      total: 1,
      limit: 50,
      offset: 0,
    } as never)
    await mockImages(100)

    render(
      <MemoryRouter>
        <PromptTab />
      </MemoryRouter>,
    )

    const more = await screen.findByRole('button', { name: '查看全部 100 张关联图片' })
    expect(more.textContent).toBe('+97')
    fireEvent.click(more)

    expect(await screen.findByText('测试 Prompt · 全部关联图片')).toBeTruthy()
    await screen.findByText('已加载 40 / 共 100 张')
  })
})
