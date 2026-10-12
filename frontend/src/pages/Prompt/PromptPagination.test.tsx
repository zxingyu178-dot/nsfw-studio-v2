import { describe, expect, it, vi } from 'vitest'
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
  },
  imageApi: { list: vi.fn(), get: vi.fn() },
}))

function makePrompt(id: string, name: string): PromptDTO {
  return {
    id,
    name,
    favorite: false,
    archived: false,
    preview_image_id: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    current_version: {
      id: `${id}_v`,
      prompt_id: id,
      version_no: 1,
      mode: 'structured',
      positive_prompt: '',
      negative_prompt: '',
      structured: { style: '', face: '', clothing: '', pose: '', scene: '', composition: '', lighting: '', extra: '' },
      created_at: '2026-01-01T00:00:00Z',
    },
  }
}

describe('PromptTab offset 分页（越过后端默认 50）', () => {
  it('加载更多可依次取回 offset=50 / 100，直到 120 条全部可达', async () => {
    const { promptApi } = await import('../../api/client')
    // 共 120 条，每页 50：0-49 / 50-99 / 100-119
    vi.mocked(promptApi.list).mockImplementation((params: { offset?: number } = {}) => {
      const offset = params.offset ?? 0
      const limit = 50
      const size = Math.min(limit, 120 - offset)
      const items = Array.from({ length: size }, (_, i) => makePrompt(`p_${offset + i}`, `Prompt ${offset + i}`))
      return Promise.resolve({ items, total: 120, limit, offset }) as never
    })
    const { container } = render(
      <MemoryRouter>
        <PromptTab />
      </MemoryRouter>,
    )

    // 第一页
    await waitFor(() => expect(container.querySelectorAll('.pp-card').length).toBe(50))
    expect(promptApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 50, offset: 0 }))

    // 第二页：offset=50
    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    await waitFor(() => expect(container.querySelectorAll('.pp-card').length).toBe(100))
    expect(promptApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 50, offset: 50 }))

    // 第三页：offset=100（最后 20 条）
    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    await waitFor(() => expect(container.querySelectorAll('.pp-card').length).toBe(120))
    expect(promptApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 50, offset: 100 }))

    // 到底：不再有“加载更多”按钮，显示全部
    await waitFor(() => expect(screen.getByText('已加载全部 120 条')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: '加载更多' })).toBeNull()
  })
})
