import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PromptTab } from './PromptTab'

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
    createEvaluation: vi.fn(),
    listEvaluations: vi.fn(),
    setStatus: vi.fn(),
  },
  imageApi: { list: vi.fn(), get: vi.fn() },
}))

async function setup() {
  const { promptApi } = await import('../../api/client')
  vi.mocked(promptApi.list).mockResolvedValue({
    items: [],
    total: 0,
    limit: 50,
    offset: 0,
  } as never)

  render(
    <MemoryRouter>
      <PromptTab />
    </MemoryRouter>,
  )

  await waitFor(() => expect(promptApi.list).toHaveBeenCalled())
  return promptApi
}

describe('Prompt 排序与状态筛选', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('初始化使用最近更新与全部状态，不发送冗余 sort/status 参数', async () => {
    const promptApi = await setup()

    expect(vi.mocked(promptApi.list).mock.calls[0][0]).toMatchObject({ offset: 0 })
    expect(vi.mocked(promptApi.list).mock.calls[0][0]).not.toHaveProperty('sort')
    expect(vi.mocked(promptApi.list).mock.calls[0][0]).not.toHaveProperty('status')
    expect(screen.getByRole('option', { name: '排序：最近更新' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '状态：全部' })).toBeInTheDocument()
  })

  it('切换为评分高到低后从 offset 0 请求 score_desc', async () => {
    const promptApi = await setup()
    vi.mocked(promptApi.list).mockClear()

    fireEvent.change(screen.getByRole('combobox', { name: 'Prompt 排序' }), {
      target: { value: 'score_desc' },
    })

    await waitFor(() =>
      expect(promptApi.list).toHaveBeenCalledWith(expect.objectContaining({ sort: 'score_desc', offset: 0 })),
    )
  })

  it('切换为保留状态后从 offset 0 请求 keep', async () => {
    const promptApi = await setup()
    vi.mocked(promptApi.list).mockClear()

    fireEvent.change(screen.getByRole('combobox', { name: 'Prompt 状态' }), {
      target: { value: 'keep' },
    })

    await waitFor(() =>
      expect(promptApi.list).toHaveBeenCalledWith(expect.objectContaining({ status: 'keep', offset: 0 })),
    )
  })
})
