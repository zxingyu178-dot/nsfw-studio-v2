import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PromptTab } from './PromptTab'
import { imageThumbUrl } from '../../types/workbench'
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

describe('Prompt 卡片封面与一键复制', () => {
  it('有 preview_image_id 时渲染 lazy 封面 img，src 为缩略图 URL', async () => {
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list).mockResolvedValue({ items: [makePrompt()] } as never)
    const { container } = renderTab()
    await screen.findByText('测试 Prompt')

    const cover = container.querySelector('img.pp-card__cover') as HTMLImageElement
    expect(cover).toBeTruthy()
    expect(cover.getAttribute('loading')).toBe('lazy')
    expect(cover.getAttribute('src')).toBe(imageThumbUrl('img_cover'))
    expect(screen.queryByText('无封面')).toBeNull()
  })

  it('无 preview_image_id 时渲染占位块', async () => {
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list).mockResolvedValue({ items: [makePrompt({ preview_image_id: null })] } as never)
    const { container } = renderTab()
    await screen.findByText('测试 Prompt')

    expect(container.querySelector('img.pp-card__cover')).toBeNull()
    expect(screen.getByText('无封面')).toBeInTheDocument()
  })

  it('点复制按钮写入完整 positive_prompt 且不打开编辑抽屉（stopPropagation）', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })

    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list).mockResolvedValue({ items: [makePrompt()] } as never)
    renderTab()
    await screen.findByText('测试 Prompt')

    fireEvent.click(screen.getByRole('button', { name: '复制' }))
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith('masterpiece, best quality, 1girl, long hair'),
    )
    // 抽屉未打开：编辑抽屉的版本历史标题不存在
    expect(screen.queryByText('版本历史（不可变；恢复 = 复制为新最新版）')).toBeNull()
    expect(screen.queryByRole('button', { name: '保存为新版本' })).toBeNull()
  })

  it('设置封面打开图片选择器并触发 setPreviewImage；移除封面触发 clearPreviewImage', async () => {
    const { promptApi } = await import('../../api/client')
    vi.mocked(promptApi.list).mockResolvedValue({ items: [makePrompt()] } as never)
    const { container } = renderTab()
    await screen.findByText('测试 Prompt')

    // 打开编辑抽屉（点击卡片），封面区块出现
    fireEvent.click(container.querySelector('.pp-card') as HTMLElement)
    expect(await screen.findByText('封面')).toBeInTheDocument()

    // 已有封面 → 移除封面
    fireEvent.click(screen.getByRole('button', { name: '移除封面' }))
    await waitFor(() => expect(promptApi.clearPreviewImage).toHaveBeenCalledWith('prm_1'))

    // 打开图片选择器（复用 ImagePickerDrawer）
    fireEvent.click(screen.getByRole('button', { name: '更换封面' }))
    expect(await screen.findByText('选择封面图片')).toBeInTheDocument()

    // 选中图片 → setPreviewImage（图片列表有 200ms 防抖，先等待渲染）
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

