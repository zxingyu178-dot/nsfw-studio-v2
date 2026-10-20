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

const PREFS_KEY = 'prompt.filters.v1'

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

describe('Prompt 筛选偏好', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('URL 为空时首屏请求使用本地偏好并写回 URL', async () => {
    localStorage.setItem(PREFS_KEY, JSON.stringify({
      q: 'portrait',
      sort: 'score_desc',
      status: 'keep',
      scored: 'true',
    }))

    const promptApi = await setup()

    expect(vi.mocked(promptApi.list).mock.calls[0][0]).toMatchObject({
      search: 'portrait',
      sort: 'score_desc',
      status: 'keep',
      scored: true,
      offset: 0,
    })
    await waitFor(() => {
      const search = screen.getByTestId('location-search').textContent ?? ''
      expect(search).toContain('q=portrait')
      expect(search).toContain('sort=score_desc')
      expect(search).toContain('status=keep')
      expect(search).toContain('scored=true')
    })
  })

  it('切换筛选时保存偏好，全部回到默认值时移除无意义记录', async () => {
    await setup()

    fireEvent.change(screen.getByPlaceholderText('搜索名称 / Prompt 内容'), {
      target: { value: 'portrait' },
    })

    await waitFor(() => expect(JSON.parse(localStorage.getItem(PREFS_KEY) ?? 'null')).toEqual({
      q: 'portrait',
      sort: 'updated_desc',
      status: '',
      scored: '',
    }))

    fireEvent.change(screen.getByRole('combobox', { name: 'Prompt 状态' }), {
      target: { value: 'keep' },
    })

    await waitFor(() => expect(JSON.parse(localStorage.getItem(PREFS_KEY) ?? 'null')).toEqual({
      q: 'portrait',
      sort: 'updated_desc',
      status: 'keep',
      scored: '',
    }))

    fireEvent.change(screen.getByPlaceholderText('搜索名称 / Prompt 内容'), {
      target: { value: '   ' },
    })

    fireEvent.change(screen.getByRole('combobox', { name: 'Prompt 状态' }), {
      target: { value: '' },
    })

    await waitFor(() => expect(localStorage.getItem(PREFS_KEY)).toBeNull())
  })

  it('URL 任一筛选参数存在时不应用本地偏好', async () => {
    localStorage.setItem(PREFS_KEY, JSON.stringify({
      q: 'local search',
      sort: 'score_desc',
      status: 'eliminated',
      scored: 'false',
    }))

    const promptApi = await setup('/prompts?sort=score_asc')

    expect(vi.mocked(promptApi.list).mock.calls[0][0]).toMatchObject({
      sort: 'score_asc',
      offset: 0,
    })
    expect(vi.mocked(promptApi.list).mock.calls[0][0]).toHaveProperty('search', undefined)
    expect(vi.mocked(promptApi.list).mock.calls[0][0]).not.toHaveProperty('status')
    expect(vi.mocked(promptApi.list).mock.calls[0][0]).not.toHaveProperty('scored')
  })

  it('重置筛选会清空 URL、本地偏好，并按默认参数重新请求', async () => {
    localStorage.setItem(PREFS_KEY, JSON.stringify({
      q: 'portrait',
      sort: 'score_desc',
      status: 'candidate',
      scored: 'true',
    }))
    const promptApi = await setup()
    vi.mocked(promptApi.list).mockClear()

    fireEvent.click(screen.getByRole('button', { name: '重置筛选' }))

    await waitFor(() => expect(screen.getByTestId('location-search')).toHaveTextContent(''))
    expect(localStorage.getItem(PREFS_KEY)).toBeNull()
    await waitFor(() => expect(promptApi.list).toHaveBeenCalled())
    const params = vi.mocked(promptApi.list).mock.calls.at(-1)?.[0]
    expect(params).toMatchObject({ offset: 0 })
    expect(params).toHaveProperty('search', undefined)
    expect(params).not.toHaveProperty('sort')
    expect(params).not.toHaveProperty('status')
    expect(params).not.toHaveProperty('scored')
  })

  it('非法 JSON 不会阻断渲染并按默认参数请求', async () => {
    localStorage.setItem(PREFS_KEY, '{not-json')

    const promptApi = await setup()

    const params = vi.mocked(promptApi.list).mock.calls[0][0]
    expect(params).toMatchObject({ offset: 0 })
    expect(params).toHaveProperty('search', undefined)
    expect(params).not.toHaveProperty('sort')
    expect(params).not.toHaveProperty('status')
    expect(params).not.toHaveProperty('scored')
  })
})
