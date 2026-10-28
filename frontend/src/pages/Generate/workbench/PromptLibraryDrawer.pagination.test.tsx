import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../../../api/client', () => ({
  ApiRequestError: class extends Error {},
  promptApi: { list: vi.fn() },
}))

import { promptApi } from '../../../api/client'
import { PAGE_SIZE, PromptLibraryDrawer } from './PromptLibraryDrawer'
import { resetWorkbench } from '../../../stores/workbenchStore'
import { emptyStructured } from '../../../types/workbench'

interface Row {
  id: string
  name: string
  favorite: boolean
  archived: boolean
  preview_image_id: null
  created_at: string
  updated_at: string
  current_version: {
    id: string
    prompt_id: string
    version_no: number
    mode: 'structured' | 'full'
    positive_prompt: string
    negative_prompt: string
    structured: ReturnType<typeof emptyStructured>
    created_at: string
  }
}

function row(index: number): Row {
  const id = `prm_${index}`
  return {
    id,
    name: `提示词 ${index}`,
    favorite: false,
    archived: false,
    preview_image_id: null,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
    current_version: {
      id: `prmv_${index}`,
      prompt_id: id,
      version_no: 1,
      mode: 'full',
      positive_prompt: `positive ${index}`,
      negative_prompt: '',
      structured: emptyStructured(),
      created_at: '2026-10-01T00:00:00Z',
    },
  }
}

/** 真分页 mock：按 offset/limit 切分，便于验证 30/50/51/200 全部可达。 */
function mockPaged(total: number): Row[] {
  const all = Array.from({ length: total }, (_, i) => row(i + 1))
  vi.mocked(promptApi.list).mockImplementation(async (params = {}) => {
    const offset = params.offset ?? 0
    const limit = params.limit ?? PAGE_SIZE
    return { items: all.slice(offset, offset + limit), total, limit, offset } as never
  })
  return all
}

beforeEach(() => {
  vi.clearAllMocks()
  resetWorkbench()
})

describe('PromptLibraryDrawer 搜索与分页（v0.37 P1-C）', () => {
  it('0 条：显示空态，不出现加载更多', async () => {
    mockPaged(0)
    render(<PromptLibraryDrawer open onClose={vi.fn()} />)
    expect(await screen.findByText(/提示词库为空/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '加载更多' })).toBeNull()
  })

  it('50 条：首屏 30，点击加载更多补齐剩余 20', async () => {
    mockPaged(50)
    render(<PromptLibraryDrawer open onClose={vi.fn()} />)

    expect(await screen.findByText('已加载 30 / 共 50 条')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))

    expect(await screen.findByText('已加载 50 / 共 50 条')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '加载更多' })).toBeNull()
    expect(vi.mocked(promptApi.list).mock.calls.map((call) => call[0]?.offset)).toEqual([0, 30])
  })

  it('51 条：第二页只补 21 条并去重', async () => {
    mockPaged(51)
    render(<PromptLibraryDrawer open onClose={vi.fn()} />)

    await screen.findByText('已加载 30 / 共 51 条')
    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    expect(await screen.findByText('已加载 51 / 共 51 条')).toBeInTheDocument()
    expect(document.querySelectorAll('.prompt-library__item')).toHaveLength(51)
  })

  it('200 条：连续加载更多全部可达', async () => {
    mockPaged(200)
    render(<PromptLibraryDrawer open onClose={vi.fn()} />)

    await screen.findByText('已加载 30 / 共 200 条')
    for (let loaded = 30; loaded < 200; loaded += 30) {
      fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
      await screen.findByText(`已加载 ${Math.min(loaded + 30, 200)} / 共 200 条`)
    }
    expect(document.querySelectorAll('.prompt-library__item')).toHaveLength(200)
    expect(screen.queryByRole('button', { name: '加载更多' })).toBeNull()
  })

  it('搜索使用服务端 search 参数并防抖，不重复请求', async () => {
    mockPaged(5)
    render(<PromptLibraryDrawer open onClose={vi.fn()} />)
    await screen.findByText('已加载 5 / 共 5 条')
    const before = vi.mocked(promptApi.list).mock.calls.length

    const input = screen.getByLabelText('搜索提示词库')
    fireEvent.change(input, { target: { value: '酒' } })
    fireEvent.change(input, { target: { value: '酒店' } })

    await waitFor(() => {
      expect(vi.mocked(promptApi.list).mock.calls.length).toBe(before + 1)
    })
    expect(vi.mocked(promptApi.list).mock.lastCall?.[0]).toMatchObject({ search: '酒店', offset: 0 })
  })

  it('旧搜索的在途响应不会覆盖新搜索结果', async () => {
    let resolveOld: (value: unknown) => void = () => {}
    vi.mocked(promptApi.list).mockImplementation((params = {}) => {
      if (params.search === '慢') {
        return new Promise((resolve) => { resolveOld = resolve }) as never
      }
      if (params.search === '快') {
        return Promise.resolve({ items: [row(2)], total: 1, limit: PAGE_SIZE, offset: 0 }) as never
      }
      return Promise.resolve({ items: [row(1)], total: 1, limit: PAGE_SIZE, offset: 0 }) as never
    })

    render(<PromptLibraryDrawer open onClose={vi.fn()} />)
    await screen.findByText('提示词 1')

    const input = screen.getByLabelText('搜索提示词库')
    fireEvent.change(input, { target: { value: '慢' } })
    await new Promise((r) => setTimeout(r, 400))
    fireEvent.change(input, { target: { value: '快' } })
    expect(await screen.findByText('提示词 2')).toBeInTheDocument()

    await act(async () => {
      resolveOld({ items: [row(3)], total: 1, limit: PAGE_SIZE, offset: 0 })
      await new Promise((r) => setTimeout(r, 50))
    })
    expect(screen.queryByText('提示词 3')).toBeNull()
    expect(screen.getByText('提示词 2')).toBeInTheDocument()
  })
})
