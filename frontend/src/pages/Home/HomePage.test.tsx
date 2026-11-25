import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { imageApi } from '../../api/client'
import type { ImageDTO } from '../../types/workbench'
import HomePage from './HomePage'

vi.mock('../../api/client', () => ({ imageApi: { list: vi.fn(), stats: vi.fn() } }))
vi.mock('../../stores/jobStore', () => ({
  useJobStore: () => ({ queue: { running: { id: 'running-job' }, queued: [{ id: 'queued-job' }], paused: [], worker: { running: true } } }),
}))

const image: ImageDTO = {
  id: 'newest', job_id: null, job_item_id: null, parent_image_id: null, kind: 'original',
  file_path: '', width: 832, height: 1216, seed: null, review_status: 'UNREVIEWED',
  status: 'NEW', favorite: false, source: 'comfyui', metadata: {},
  created_at: '2026-11-24T09:30:00.000Z', updated_at: '2026-11-24T09:30:00.000Z',
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(imageApi.list).mockImplementation(async ({ status } = {}) => ({
    items: status === 'NEW' ? [image] : [], total: status === 'NEW' ? 1 : 0, page: 1, page_size: 7, has_next: false,
  }))
  vi.mocked(imageApi.stats).mockImplementation(async (params) => ({
    total: params?.date_from ? 7 : 82, new: 24, keep: 55, reject: 3, archived: 0, favorites: 0,
  }))
})

function openHome() {
  render(<MemoryRouter><HomePage /></MemoryRouter>)
}

describe('首页', () => {
  it('使用真实接口的计数和预览地址，提供待审与废片快捷入口', async () => {
    openHome()
    expect(await screen.findByText('24')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
    expect(imageApi.stats).toHaveBeenCalledWith(expect.objectContaining({ date_from: expect.any(String), source: 'comfyui' }))
    expect(screen.getByAltText('最新作品').getAttribute('src')).toBe('/api/v1/images/newest/preview')
    expect(screen.getByRole('link', { name: '继续审核' })).toHaveAttribute('href', '/gallery?status=NEW&review=1')
    expect(screen.getByRole('link', { name: /废片/ })).toHaveAttribute('href', '/gallery?status=REJECT')
    expect(screen.getByRole('link', { name: /1 运行.*1 排队/ })).toHaveAttribute('href', '/generate')
  })

  it('请求失败后显示重试，重试成功时恢复服务器数据', async () => {
    vi.mocked(imageApi.stats).mockRejectedValueOnce(new Error('offline'))
    openHome()
    expect(await screen.findByRole('alert')).toHaveTextContent('加载失败')
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(await screen.findByText('24')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
