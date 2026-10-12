import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AssetsPage from './AssetsPage'
import type { AssetDTO } from '../../types/workbench'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {},
  assetApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    updateMeta: vi.fn(),
    archive: vi.fn(),
    restore: vi.fn(),
    listVersions: vi.fn(),
    addVersion: vi.fn(),
    workbench: vi.fn(),
  },
  imageApi: { list: vi.fn() },
}))

function makeAsset(id: string, name: string): AssetDTO {
  return {
    id,
    type: 'clothing',
    name,
    favorite: false,
    archived: false,
    source_image_id: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    current_version: null,
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AssetsPage />
    </MemoryRouter>,
  )
}

describe('AssetsPage offset 分页（移除前端 limit=100 隐形上限）', () => {
  it('加载更多取回 offset=60，越过 100 条上限可达 120', async () => {
    const { assetApi } = await import('../../api/client')
    // 共 120 条，每页 60（>100 默认上限）
    vi.mocked(assetApi.list).mockImplementation((params: { offset?: number } = {}) => {
      const offset = params.offset ?? 0
      const limit = 60
      const size = Math.min(limit, 120 - offset)
      const items = Array.from({ length: size }, (_, i) => makeAsset(`a_${offset + i}`, `素材 ${offset + i}`))
      return Promise.resolve({ items, total: 120, limit, offset }) as never
    })

    const { container } = renderPage()

    await waitFor(() => expect(container.querySelectorAll('.as-card').length).toBe(60))
    expect(assetApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 60, offset: 0 }))

    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    await waitFor(() => expect(container.querySelectorAll('.as-card').length).toBe(120))
    expect(assetApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 60, offset: 60 }))

    await waitFor(() => expect(screen.getByText('已加载全部 120 条')).toBeInTheDocument())
  })

  it('搜索 stale guard：旧搜索条件晚返回的结果不覆盖新列表', async () => {
    const { assetApi } = await import('../../api/client')
    const calls: Array<{ params: { search?: string }; resolve: (v: any) => void }> = []
    vi.mocked(assetApi.list).mockImplementation(
      (params: { search?: string } = {}) =>
        new Promise((resolve) => calls.push({ params, resolve })),
    )

    renderPage()

    // 初次列表请求（空搜索）
    await waitFor(() => expect(calls.length).toBe(1))

    // 输入新搜索词 → 防抖后触发新请求
    fireEvent.change(screen.getByPlaceholderText('搜索素材名称 / Prompt'), {
      target: { value: 'xyz' },
    })
    await waitFor(() => expect(calls.length).toBe(2), { timeout: 2000 })
    expect(calls[1].params.search).toBe('xyz')

    // 旧请求（空搜索）此时才晚返回 —— 必须被丢弃
    calls[0].resolve({ items: [makeAsset('stale', '旧请求结果')], total: 1, limit: 60, offset: 0 })
    await waitFor(() => expect(screen.queryByText('旧请求结果')).toBeNull())

    // 新请求返回 —— 正确渲染
    calls[1].resolve({ items: [makeAsset('fresh', '新搜索结果')], total: 1, limit: 60, offset: 0 })
    await screen.findByText('新搜索结果')
    expect(screen.queryByText('旧请求结果')).toBeNull()
  })
})
