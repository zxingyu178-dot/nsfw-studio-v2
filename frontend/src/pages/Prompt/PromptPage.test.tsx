import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import PromptPage from './PromptPage'

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
  },
  recipeApi: {
    list: vi.fn(),
    listVersions: vi.fn(),
    updateMeta: vi.fn(),
    archive: vi.fn(),
    restore: vi.fn(),
    restoreVersion: vi.fn(),
  },
  historyApi: { list: vi.fn() },
  imageApi: { list: vi.fn(), get: vi.fn() },
  jobApi: {},
  moduleApi: { list: vi.fn() },
}))

beforeEach(async () => {
  const { promptApi, recipeApi, historyApi } = await import('../../api/client')
  vi.mocked(promptApi.list).mockResolvedValue({ items: [] } as never)
  vi.mocked(recipeApi.list).mockResolvedValue({ items: [] } as never)
  vi.mocked(historyApi.list).mockResolvedValue({ items: [], total: 0 } as never)
})

function renderPage() {
  return render(
    <MemoryRouter>
      <PromptPage />
    </MemoryRouter>
  )
}

describe('PromptPage 提示词中心', () => {
  it('三个页签可切换，各自显示空状态', async () => {
    renderPage()
    expect(await screen.findByText('还没有 Prompt')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: '配方' }))
    expect(await screen.findByText('还没有配方')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: '历史' }))
    expect(await screen.findByText('暂无生成历史')).toBeInTheDocument()
  })

  it('点击新建 Prompt 打开编辑抽屉', async () => {
    renderPage()
    await screen.findByText('还没有 Prompt')
    fireEvent.click(screen.getByRole('button', { name: '新建 Prompt' }))
    expect((await screen.findAllByText('新建 Prompt')).length).toBeGreaterThanOrEqual(2)
    expect(screen.getByRole('button', { name: '创建' })).toBeInTheDocument()
  })
})
