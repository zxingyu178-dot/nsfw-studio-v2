/**
 * v0.15.1：把旧 ResultPane.lightbox 的 Lightbox / rendition 行为迁移到 Workbench 4.0
 * 生产路径（CanvasStage）：
 * - 主查看走 preview rendition，底部 filmstrip 走 thumbnail + lazy；
 * - 触发全屏（onFullscreen）打开 Lightbox，定位到当前 shown 图，ESC 关闭。
 * 主预览 onError 回退原图的 rendition 细节由 CanvasViewport 自身测试覆盖。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const mockUseJobStore = vi.fn()

vi.mock('../../../stores/jobStore', () => ({
  useJobStore: () => mockUseJobStore(),
  activeJob: (store: { trackedJob?: unknown; queue?: { running?: unknown } | null }) =>
    store.trackedJob ?? store.queue?.running ?? null,
  trackJob: vi.fn(),
}))

// CanvasViewport 打桩：回显主图 rendition，并暴露一个全屏入口调用 onFullscreen。
vi.mock('../../../components/CanvasViewport/CanvasViewport', () => ({
  CanvasViewport: ({ imageUrl, onFullscreen }: { imageUrl: string; onFullscreen: () => void }) => (
    <div data-testid="canvas-viewport">
      <img src={imageUrl} alt="主图" />
      <button type="button" onClick={onFullscreen}>全屏查看</button>
    </div>
  ),
}))

vi.mock('../../../api/client', () => ({
  ApiRequestError: class extends Error {},
  imageApi: {
    list: vi.fn(async () => ({ items: images, total: 2 })),
    favorite: vi.fn(),
    setStatus: vi.fn(),
    get: vi.fn(),
  },
  jobApi: {
    get: vi.fn(async (id: string) => ({ id, resume_of_job_id: null })),
  },
}))

import { CanvasStage } from './CanvasStage'
import { imagePreviewUrl, imageThumbUrl } from '../../../types/workbench'

function img(id: string, created: string) {
  return {
    id, job_id: 'job_1', kind: 'original', file_path: `/tmp/${id}.png`,
    width: 800, height: 600, seed: 1, favorite: false, status: 'NEW',
    created_at: created, updated_at: created,
  }
}

const images = [img('img_a', '2026-01-01T00:00:00'), img('img_b', '2026-01-01T00:01:00')]

beforeEach(() => vi.clearAllMocks())

function renderStage() {
  return render(
    <MemoryRouter>
      <CanvasStage />
    </MemoryRouter>,
  )
}

describe('CanvasStage Lightbox / rendition（生产路径）', () => {
  it('主查看用 preview、filmstrip 用 thumbnail+lazy；全屏打开 Lightbox 定位 shown，ESC 关闭', async () => {
    const completed = {
      id: 'job_1', status: 'COMPLETED', completed_count: 2, positive_prompt_snapshot: 'p',
      module_id: 'basic_generate', stages: [{ completed_count: 2 }],
    }
    mockUseJobStore.mockReturnValue({
      trackedJob: completed,
      queue: { running: null, queued: [], paused: [] },
      liveProgressByStageItem: {},
    })
    const { container } = renderStage()

    // 主查看：preview rendition（shown 默认最后一张 img_b）
    const mainImg = await waitFor(() => {
      const el = container.querySelector('[data-testid="canvas-viewport"] img') as HTMLImageElement
      expect(el).toBeTruthy()
      return el
    })
    expect(mainImg.getAttribute('src')).toBe(imagePreviewUrl('img_b'))

    // filmstrip：thumbnail + lazy
    const thumbs = await waitFor(() => {
      const list = container.querySelectorAll('.wb4-filmstrip img')
      expect(list.length).toBe(2)
      return list
    })
    expect(thumbs[0].getAttribute('src')).toBe(imageThumbUrl('img_a'))
    expect(thumbs[0].getAttribute('loading')).toBe('lazy')

    // 全屏打开 Lightbox，定位 shown（img_b）
    fireEvent.click(screen.getByRole('button', { name: '全屏查看' }))
    const lightbox = await screen.findByRole('dialog', { name: '图片预览' })
    expect(lightbox).toBeInTheDocument()
    expect(lightbox.querySelector('img')?.getAttribute('src')).toBe(imagePreviewUrl('img_b'))

    // ESC 关闭
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: '图片预览' })).not.toBeInTheDocument()
    })
  })
})
