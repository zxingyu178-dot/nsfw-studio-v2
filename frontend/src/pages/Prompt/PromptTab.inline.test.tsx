import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PromptTab } from './PromptTab'
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
    listImages: vi.fn(),
    setStatus: vi.fn(),
  },
  imageApi: { list: vi.fn(), get: vi.fn() },
}))

function makePrompt(overrides: Partial<PromptDTO> = {}): PromptDTO {
  return {
    id: 'prm_1',
    name: '原始名称',
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
      positive_prompt: 'masterpiece, 1girl',
      negative_prompt: '',
      structured: { style: '', face: '', clothing: '', pose: '', scene: '', composition: '', lighting: '', extra: '' },
      created_at: '2026-01-01T00:00:00Z',
    },
    status: 'candidate',
    ...overrides,
  }
}

async function setup(prompt: PromptDTO) {
  const { promptApi } = await import('../../api/client')
  vi.mocked(promptApi.list).mockResolvedValue({
    items: [prompt],
    total: 1,
    limit: 50,
    offset: 0,
  } as never)
  render(
    <MemoryRouter>
      <PromptTab />
    </MemoryRouter>,
  )
  return promptApi
}

describe('Prompt 卡片：卡片内改名与状态切换（v0.37.6）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('点击名称进入编辑，Enter 保存并就地更新卡片', async () => {
    const promptApi = await setup(makePrompt())
    vi.mocked(promptApi.updateMeta).mockResolvedValue(makePrompt({ name: '新名称' }) as never)

    fireEvent.click(await screen.findByRole('button', { name: '原始名称' }))
    const input = screen.getByLabelText('重命名 Prompt')
    fireEvent.change(input, { target: { value: '新名称' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() =>
      expect(promptApi.updateMeta).toHaveBeenCalledWith('prm_1', { name: '新名称' }),
    )
    expect(await screen.findByRole('button', { name: '新名称' })).toBeTruthy()
  })

  it('Esc 取消改名，不请求后端', async () => {
    const promptApi = await setup(makePrompt())

    fireEvent.click(await screen.findByRole('button', { name: '原始名称' }))
    const input = screen.getByLabelText('重命名 Prompt')
    fireEvent.change(input, { target: { value: '不应保存' } })
    fireEvent.keyDown(input, { key: 'Escape' })

    expect(promptApi.updateMeta).not.toHaveBeenCalled()
    expect(await screen.findByRole('button', { name: '原始名称' })).toBeTruthy()
  })

  it('状态下拉直接切换并调用后端', async () => {
    const promptApi = await setup(makePrompt())
    vi.mocked(promptApi.setStatus).mockResolvedValue(makePrompt({ status: 'keep' }) as never)

    const select = (await screen.findByLabelText('提示词状态')) as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'keep' } })

    await waitFor(() => expect(promptApi.setStatus).toHaveBeenCalledWith('prm_1', { status: 'keep' }))
    await waitFor(() => expect(select.value).toBe('keep'))
  })

  it('状态更新失败时回滚并提示错误', async () => {
    const promptApi = await setup(makePrompt())
    vi.mocked(promptApi.setStatus).mockRejectedValue(new Error('network down'))

    const select = (await screen.findByLabelText('提示词状态')) as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'eliminated' } })

    await waitFor(() => expect(select.value).toBe('candidate'))
    expect(await screen.findByText('更新状态失败')).toBeTruthy()
  })
})
