import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AssetsPage from './AssetsPage'

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

beforeEach(async () => {
  const { assetApi } = await import('../../api/client')
  vi.mocked(assetApi.list).mockResolvedValue({ items: [] } as never)
})

function renderPage() {
  return render(
    <MemoryRouter>
      <AssetsPage />
    </MemoryRouter>
  )
}

describe('AssetsPage 素材库', () => {
  it('渲染分类标签与工具栏，无素材时显示空状态', async () => {
    renderPage()
    expect(screen.getByText('全部')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '上传素材' })).toBeInTheDocument()
    expect(await screen.findByText('还没有素材')).toBeInTheDocument()
  })

  it('点击上传素材打开上传对话框', async () => {
    renderPage()
    await screen.findByText('还没有素材')
    fireEvent.click(screen.getByRole('button', { name: '上传素材' }))
    expect((await screen.findAllByText('上传素材')).length).toBeGreaterThanOrEqual(2)
    expect(screen.getByRole('button', { name: '创建' })).toBeInTheDocument()
  })
})
