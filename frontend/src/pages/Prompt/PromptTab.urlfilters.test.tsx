import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
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

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location-search">{location.search}</output>
}

async function setup(initialEntry = '/prompts') {
  const { promptApi } = await import('../../api/client')
  vi.mocked(promptApi.list).mockResolvedValue({
    items: [],
    total: 0,
    limit: 50,
    offset: 0,
  } as never)

  render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <PromptTab />
      <LocationProbe />
    </MemoryRouter>,
  )

  await waitFor(() => expect(promptApi.list).toHaveBeenCalled())
  return promptApi
}

describe('Prompt URL 筛选', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('从 URL 读取排序与状态并用于首次请求', async () => {
    const promptApi = await setup('/prompts?sort=score_desc&status=keep')

    expect(vi.mocked(promptApi.list).mock.calls[0][0]).toMatchObject({
      sort: 'score_desc',
      status: 'keep',
      offset: 0,
    })
  })

  it('从 URL 读取 scored=false 并以布尔值用于首次请求', async () => {
    const promptApi = await setup('/prompts?scored=false')

    expect(vi.mocked(promptApi.list).mock.calls[0][0]).toMatchObject({
      scored: false,
      offset: 0,
    })
  })

  it('切换为仅已评分时更新请求与 URL', async () => {
    const promptApi = await setup()
    vi.mocked(promptApi.list).mockClear()

    fireEvent.change(screen.getByRole('combobox', { name: '已评分' }), {
      target: { value: 'true' },
    })

    await waitFor(() =>
      expect(promptApi.list).toHaveBeenCalledWith(expect.objectContaining({ scored: true, offset: 0 })),
    )
    expect(screen.getByTestId('location-search')).toHaveTextContent('scored=true')
  })

  it('排序切回最近更新时从 URL 与请求中移除默认 sort', async () => {
    const promptApi = await setup('/prompts?sort=score_desc')
    vi.mocked(promptApi.list).mockClear()

    fireEvent.change(screen.getByRole('combobox', { name: 'Prompt 排序' }), {
      target: { value: 'updated_desc' },
    })

    await waitFor(() => expect(promptApi.list).toHaveBeenCalled())
    const params = vi.mocked(promptApi.list).mock.calls.at(-1)?.[0]
    expect(params).not.toHaveProperty('sort')
    expect(screen.getByTestId('location-search').textContent).not.toContain('sort=')
  })

  it('首次进入时清理显式默认值与无效筛选值', async () => {
    await setup('/prompts?q=&sort=updated_desc&status=unknown&scored=unknown&tab=mine')

    await waitFor(() => expect(screen.getByTestId('location-search')).toHaveTextContent('?tab=mine'))
  })
})
