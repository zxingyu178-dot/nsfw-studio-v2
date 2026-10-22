import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PromptTab } from './PromptTab'
import { imagePreviewUrl, imageThumbUrl } from '../../types/workbench'
import type { PromptDTO } from '../../types/workbench'

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

function makePrompt(overrides: Partial<PromptDTO> = {}): PromptDTO {
  return {
    id: 'prm_1',
    name: '测试 Prompt',
    favorite: false,
    archived: false,
    preview_image_id: 'img_cover',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    current_version: {
      id: 'prmv_1',
      prompt_id: 'prm_1',
      version_no: 1,
      mode: 'full',
      positive_prompt: 'masterpiece, best quality, 1girl, long hair',
      negative_prompt: 'blur',
      structured: { style: '', face: '', clothing: '', pose: '', scene: '', composition: '', lighting: '', extra: '' },
      created_at: '2026-01-01T00:00:00Z',
    },
    ...overrides,
  }
}

beforeEach(async () => {
  const { promptApi, imageApi } = await import('../../api/client')
  vi.mocked(promptApi.get).mockResolvedValue(makePrompt() as never)
  vi.mocked(promptApi.listVersions).mockResolvedValue([] as never)
  vi.mocked(promptApi.setPreviewImage).mockResolvedValue(makePrompt({ preview_image_id: 'img_picked' }) as never)
  vi.mocked(promptApi.clearPreviewImage).mockResolvedValue(makePrompt({ preview_image_id: null }) as never)
  vi.mocked(imageApi.list).mockResolvedValue({
    items: [{ id: 'img_picked', kind: 'original', width: 100, height: 100, favorite: false }],
  } as never)
})

function renderTab() {
  return render(
    <MemoryRouter>
      <PromptTab />
    </MemoryRouter>,
  )
}

describe('Prompt 可视化卡片（整行布局，封面位于摘要下方）', () => {
  it('有 preview_image_id：预览图用 thumbnail，DOM 位于名称/摘要之后', async () => {
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list).mockResolvedValue({ items: [makePrompt()] } as never)
    const { container } = renderTab()
    await screen.findByText('测试 Prompt')

    const card = container.querySelector('.pp-card') as HTMLElement
    const head = card.querySelector('.pp-card__head') as HTMLElement
    const excerpt = card.querySelector('.pp-card__excerpt') as HTMLElement
    const preview = card.querySelector('.pp-card__preview') as HTMLElement
    const img = preview.querySelector('img') as HTMLImageElement
    expect(img).toBeTruthy()
    expect(img.getAttribute('loading')).toBe('lazy')
    expect(img.getAttribute('src')).toBe(imageThumbUrl('img_cover'))
    // DOM 与视觉顺序均为 head → excerpt → preview。
    expect(head.compareDocumentPosition(excerpt) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(excerpt.compareDocumentPosition(preview) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // 不再使用旧的顶部封面
    expect(card.querySelector('.pp-card__cover')).toBeNull()
  })

  it('无 preview_image_id：不渲染任何媒体区或占位', async () => {
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list).mockResolvedValue({ items: [makePrompt({ preview_image_id: null })] } as never)
    const { container } = renderTab()
    await screen.findByText('测试 Prompt')

    expect(screen.queryByText('暂未生成')).toBeNull()
    expect(screen.queryByText('无封面')).toBeNull()
    expect(container.querySelector('.pp-card__preview')).toBeNull()
    expect(container.querySelector('.pp-card__preview--empty')).toBeNull()
  })

  it('有 preview_image_id 但缩略图加载失败（onError）→ 移除整个媒体区，不渲染占位', async () => {
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list).mockResolvedValue({ items: [makePrompt()] } as never)
    const { container } = renderTab()
    await screen.findByText('测试 Prompt')

    const img = container.querySelector('.pp-card__preview img') as HTMLImageElement
    expect(img).toBeTruthy()
    fireEvent.error(img) // 模拟 rendition 缺失/损坏

    expect(screen.queryByText('暂未生成')).toBeNull()
    expect(container.querySelector('.pp-card__preview')).toBeNull()
    expect(container.querySelector('.pp-card__preview--empty')).toBeNull()
  })

  it('v0.15.1：编辑抽屉小封面使用 preview（1536 渐进图）而非 original content，降低 IO', async () => {
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list).mockResolvedValue({ items: [makePrompt()] } as never)
    const { container } = renderTab()
    await screen.findByText('测试 Prompt')

    fireEvent.click(screen.getByRole('button', { name: '编辑' }))
    const coverImg = await waitFor(() => container.querySelector('.pp-cover__img') as HTMLImageElement)
    expect(coverImg).toBeTruthy()
    expect(coverImg.getAttribute('src')).toBe(imagePreviewUrl('img_cover'))
    expect(coverImg.getAttribute('src')).not.toContain('/content')
  })

  it('已归档 Prompt 仍显示在卡片网格中（含已归档徽标）', async () => {
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list).mockResolvedValue({ items: [makePrompt({ archived: true })] } as never)
    renderTab()
    await screen.findByText('测试 Prompt')
    expect(screen.getByText('已归档')).toBeInTheDocument()
  })

  it('点预览图打开大图预览；无图不提供可点击预览', async () => {
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list).mockResolvedValue({ items: [makePrompt()] } as never)
    renderTab()
    await screen.findByText('测试 Prompt')
    fireEvent.click(screen.getByRole('button', { name: /预览 .* 的封面/ }))
    expect((await screen.findByRole('dialog')).querySelector('img')).toBeTruthy()
  })

  it('复制按钮写入完整 positive_prompt 且不打开编辑抽屉', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list).mockResolvedValue({ items: [makePrompt()] } as never)
    renderTab()
    await screen.findByText('测试 Prompt')

    fireEvent.click(screen.getByRole('button', { name: '复制' }))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('masterpiece, best quality, 1girl, long hair'))
    expect(screen.queryByText('版本历史（不可变；恢复 = 复制为新最新版）')).toBeNull()
  })

  it('“编辑”打开抽屉，封面仍显式“设为 Prompt 封面”（不自动覆盖）', async () => {
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list).mockResolvedValue({ items: [makePrompt({ preview_image_id: null })] } as never)
    const { container } = renderTab()
    await screen.findByText('测试 Prompt')

    fireEvent.click(screen.getByRole('button', { name: '编辑' }))
    expect(await screen.findByText('封面')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '设置封面' })).toBeInTheDocument()
    // 选图 → setPreviewImage
    fireEvent.click(screen.getByRole('button', { name: '设置封面' }))
    expect(await screen.findByText('选择封面图片')).toBeInTheDocument()
    await waitFor(() => expect(container.querySelector('.wb-image-item')).not.toBeNull())
    fireEvent.click(container.querySelector('.wb-image-item') as HTMLElement)
    await waitFor(() => expect(promptApi.setPreviewImage).toHaveBeenCalledWith('prm_1', 'img_picked'))
  })
})

describe('新建 Prompt 后立即刷新列表', () => {
  it('创建成功后重新拉取列表（onChanged），新卡片无需手动刷新即出现', async () => {
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list).mockResolvedValue({ items: [] } as never)
    vi.mocked(promptApi.create).mockResolvedValue(
      makePrompt({ id: 'prm_new', name: '新建的猫' }) as never)
    const { container } = renderTab()

    fireEvent.click(screen.getByRole('button', { name: '新建 Prompt' }))
    const drawer = container.querySelector('.ds-drawer') as HTMLElement
    expect(drawer).toBeTruthy()
    fireEvent.change(drawer.querySelector('input') as HTMLInputElement, {
      target: { value: '新建的猫' },
    })
    fireEvent.change(drawer.querySelector('textarea') as HTMLTextAreaElement, {
      target: { value: 'masterpiece, best quality, a cat' },
    })

    const callsBefore = vi.mocked(promptApi.list).mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: '创建' }))

    await waitFor(() =>
      expect(vi.mocked(promptApi.list).mock.calls.length).toBeGreaterThan(callsBefore))
    expect(promptApi.create).toHaveBeenCalledTimes(1)
  })
})
