import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { assetApi } from '../../api/client'
import { AssetPickerDrawer } from './AssetPickerDrawer'
import type { AssetDTO } from '../../types/workbench'

vi.mock('../../api/client', () => ({
  assetApi: { list: vi.fn() },
  ApiRequestError: class extends Error {},
}))

function makeAsset(id: string): AssetDTO {
  return {
    id,
    asset_type: 'face',
    name: `素材 ${id}`,
    favorite: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    current_version: { id: `v-${id}`, version_index: 1, prompt_text: `prompt ${id}`, note: '', created_at: '2026-01-01T00:00:00Z' },
  } as unknown as AssetDTO
}

describe('AssetPickerDrawer 分页（Phase 0.12 任务 10.5）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('去掉 limit=60 隐形上限：首页 60 条后可“加载更多”取到第 61 个', async () => {
    const first = Array.from({ length: 60 }, (_, i) => makeAsset(`a${i}`))
    ;(assetApi.list as unknown as ReturnType<typeof vi.fn>).mockImplementation((params: { offset?: number }) => {
      const off = params.offset ?? 0
      if (off >= 60) return Promise.resolve({ items: [makeAsset('a60')], total: 61, limit: 60, offset: off })
      return Promise.resolve({ items: first, total: 61, limit: 60, offset: 0 })
    })

    render(<AssetPickerDrawer slot="face" onClose={() => {}} onPicked={() => {}} />)

    await waitFor(() => expect(screen.getByText('素材 a59')).toBeTruthy())
    // 首页满 60 条 → 出现“加载更多”
    const more = await screen.findByRole('button', { name: /加载更多/ })
    fireEvent.click(more)

    await waitFor(() => expect(screen.getByText('素材 a60')).toBeTruthy())
    // 点击“加载更多”那次请求带 offset=60，证明不是硬卡 60 条
    const calls = (assetApi.list as unknown as ReturnType<typeof vi.fn>).mock.calls
    const moreCall = calls.find((call) => (call[0] as { offset?: number }).offset === 60)
    expect(moreCall).toBeTruthy()
    // 末页未满 60 → 不再显示“加载更多”
    await waitFor(() => expect(screen.queryByRole('button', { name: /加载更多/ })).toBeNull())
  })

  it('搜索切换 stale guard：连续搜索丢弃过期响应，不把旧页拼进新结果', async () => {
    const slowOld = new Promise<{ items: AssetDTO[]; total: number; limit: number; offset: number }>(() => {})
    const fresh = { items: [makeAsset('only')], total: 1, limit: 60, offset: 0 }
    ;(assetApi.list as unknown as ReturnType<typeof vi.fn>)
      .mockReturnValueOnce(slowOld)
      .mockResolvedValueOnce(fresh)

    render(<AssetPickerDrawer slot="face" onClose={() => {}} onPicked={() => {}} />)
    const input = screen.getByPlaceholderText('搜索素材名称 / Prompt')
    // 触发首次加载后立即输入新搜索
    fireEvent.change(input, { target: { value: 'only' } })

    await waitFor(() => expect(screen.getByText('素材 only')).toBeTruthy())
    // 旧的 slowOld 永不 resolve；即便 resolve 也会被 reqId 丢弃
    expect(screen.queryByText('素材 a0')).toBeNull()
  })
})
