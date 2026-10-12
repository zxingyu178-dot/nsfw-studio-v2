import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { RecipeTab } from './RecipeTab'
import type { RecipeDTO } from '../../types/workbench'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {},
  recipeApi: {
    list: vi.fn(),
    listVersions: vi.fn(),
    updateMeta: vi.fn(),
    archive: vi.fn(),
    restore: vi.fn(),
    restoreVersion: vi.fn(),
  },
}))

function makeRecipe(id: string, name: string): RecipeDTO {
  return {
    id,
    name,
    favorite: false,
    archived: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    current_version: null,
  }
}

describe('RecipeTab offset 分页（越过后端默认 50）', () => {
  it('加载更多取回 offset=50，越过默认上限可达 100 条', async () => {
    const { recipeApi } = await import('../../api/client')
    // 共 100 条，每页 50
    vi.mocked(recipeApi.list).mockImplementation((params: { offset?: number } = {}) => {
      const offset = params.offset ?? 0
      const limit = 50
      const size = Math.min(limit, 100 - offset)
      const items = Array.from({ length: size }, (_, i) => makeRecipe(`r_${offset + i}`, `配方 ${offset + i}`))
      return Promise.resolve({ items, total: 100, limit, offset }) as never
    })

    const { container } = render(
      <MemoryRouter>
        <RecipeTab />
      </MemoryRouter>,
    )

    await waitFor(() => expect(container.querySelectorAll('.pp-card').length).toBe(50))
    expect(recipeApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 50, offset: 0 }))

    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    await waitFor(() => expect(container.querySelectorAll('.pp-card').length).toBe(100))
    expect(recipeApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 50, offset: 50 }))

    await waitFor(() => expect(screen.getByText('已加载全部 100 条')).toBeInTheDocument())
  })
})
