import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../../../api/client', () => ({
  ApiRequestError: class extends Error {},
  promptApi: { list: vi.fn() },
}))

import { promptApi } from '../../../api/client'
import { PromptLibraryDrawer } from './PromptLibraryDrawer'
import { getWorkbenchState, resetWorkbench } from '../../../stores/workbenchStore'
import { emptyStructured } from '../../../types/workbench'

function promptStructured() {
  return {
    id: 'prm_1',
    name: '酒店走廊',
    favorite: false,
    archived: false,
    preview_image_id: null,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
    current_version: {
      id: 'prmv_1',
      prompt_id: 'prm_1',
      version_no: 1,
      mode: 'structured',
      positive_prompt: 'structured-positive',
      negative_prompt: 'bad anatomy',
      structured: { ...emptyStructured(), style: '写实摄影', scene: '酒店走廊' },
      created_at: '2026-10-01T00:00:00Z',
    },
  }
}

function promptFull() {
  return {
    id: 'prm_2',
    name: '完整提示词',
    favorite: true,
    archived: false,
    preview_image_id: null,
    created_at: '2026-10-02T00:00:00Z',
    updated_at: '2026-10-02T00:00:00Z',
    current_version: {
      id: 'prmv_2',
      prompt_id: 'prm_2',
      version_no: 2,
      mode: 'full',
      positive_prompt: 'full-positive prompt',
      negative_prompt: '',
      structured: emptyStructured(),
      created_at: '2026-10-02T00:00:00Z',
    },
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  resetWorkbench()
})

describe('PromptLibraryDrawer 一键填入', () => {
  it('结构化提示词：逐字段回填 + negative + 来源记录，并关闭', async () => {
    vi.mocked(promptApi.list).mockResolvedValue({ items: [promptStructured()] } as never)
    const onClose = vi.fn()
    render(<PromptLibraryDrawer open onClose={onClose} />)
    const pick = await screen.findByText('酒店走廊')
    fireEvent.click(pick)

    await waitFor(() => {
      const state = getWorkbenchState()
      expect(state.promptMode).toBe('structured')
      expect(state.structured.style).toBe('写实摄影')
      expect(state.structured.scene).toBe('酒店走廊')
      expect(state.negativePrompt).toBe('bad anatomy')
      expect(state.sourcePromptId).toBe('prm_1')
      expect(state.sourcePromptVersionId).toBe('prmv_1')
    })
    expect(onClose).toHaveBeenCalled()
  })

  it('完整提示词：回填 fullPrompt 并切到完整模式', async () => {
    vi.mocked(promptApi.list).mockResolvedValue({ items: [promptFull()] } as never)
    const onClose = vi.fn()
    render(<PromptLibraryDrawer open onClose={onClose} />)
    fireEvent.click(await screen.findByRole('button', { name: '填入' }))

    await waitFor(() => {
      const state = getWorkbenchState()
      expect(state.promptMode).toBe('full')
      expect(state.fullPrompt).toBe('full-positive prompt')
      expect(state.sourcePromptId).toBe('prm_2')
    })
    expect(onClose).toHaveBeenCalled()
  })

  it('列表为空时给出空态提示', async () => {
    vi.mocked(promptApi.list).mockResolvedValue({ items: [] } as never)
    render(<PromptLibraryDrawer open onClose={vi.fn()} />)
    expect(await screen.findByText(/提示词库为空/)).toBeInTheDocument()
  })
})
