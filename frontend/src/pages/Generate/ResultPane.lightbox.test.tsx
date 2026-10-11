import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { imageApi } from '../../api/client'
import { ResultPane } from './ResultPane'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {},
  imageApi: { list: vi.fn() },
}))

const mockUseJobStore = vi.fn()
const mockActiveJob = vi.fn()
vi.mock('../../stores/jobStore', () => ({
  useJobStore: (...args: unknown[]) => mockUseJobStore(...args),
  activeJob: (...args: unknown[]) => mockActiveJob(...args),
}))

function img(id: string, created: string) {
  return {
    id,
    job_id: 'job_1',
    job_item_id: null,
    parent_image_id: null,
    kind: 'original',
    file_path: `/tmp/${id}.png`,
    width: 800,
    height: 600,
    seed: 1,
    review_status: 'UNREVIEWED',
    favorite: false,
    source: 'comfyui',
    metadata: {},
    created_at: created,
    updated_at: created,
  }
}

const job = {
  id: 'job_1',
  resume_of_job_id: null,
  completed_count: 2,
  status: 'COMPLETED',
    items: [],
  stages: [{ completed_count: 2 }],
}

const images = [img('img_a', '2026-01-01T00:00:00'), img('img_b', '2026-01-01T00:01:00')]

beforeEach(() => {
  vi.clearAllMocks()
  mockUseJobStore.mockReturnValue({})
  vi.mocked(mockActiveJob).mockReturnValue(job as never)
  vi.mocked(imageApi.list).mockResolvedValue({ items: images, total: 2 } as never)
})

describe('ResultPane 双击主图打开 Lightbox', () => {
  it('双击 result-stage 主图打开 Lightbox，定位到当前 shown 图', async () => {
    const { container } = render(
      <MemoryRouter>
        <ResultPane />
      </MemoryRouter>
    )

    // shown 默认取最后一张 img_b
    const stage = (await waitFor(() => {
      const el = container.querySelector('.result-stage')
      expect(el).toBeTruthy()
      return el as HTMLElement
    })) as HTMLElement
    expect(stage.querySelector('img')?.getAttribute('src')).toBe('/api/v1/images/img_b/content')

    fireEvent.doubleClick(stage)

    const lightbox = await screen.findByRole('dialog', { name: '图片预览' })
    expect(lightbox).toBeInTheDocument()
    // 定位到 shown（img_b，index 1）
    expect(lightbox.querySelector('img')?.getAttribute('src')).toBe('/api/v1/images/img_b/content')
    expect(lightbox.querySelectorAll('img')).toHaveLength(1)

    // ESC 关闭
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: '图片预览' })).not.toBeInTheDocument()
    })
  })
})
