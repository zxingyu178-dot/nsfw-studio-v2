/**
 * CanvasStage 键盘切换：←/→ 在 Canvas 内切换当前图片；输入框聚焦时不拦截。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { fireEvent, render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const mockUseJobStore = vi.fn()

vi.mock('../../../stores/jobStore', () => ({
  useJobStore: () => mockUseJobStore(),
  activeJob: (store: { trackedJob?: unknown; queue?: { running?: unknown } | null }) =>
    store.trackedJob ?? store.queue?.running ?? null,
  trackJob: vi.fn(),
}))

vi.mock('../../../components/CanvasViewport/CanvasViewport', () => ({
  CanvasViewport: ({ imageUrl }: { imageUrl: string }) => (
    <div data-testid="canvas-viewport"><img src={imageUrl} alt="主图" /></div>
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
  jobApi: { get: vi.fn(async (id: string) => ({ id, resume_of_job_id: null })) },
}))

import { CanvasStage } from './CanvasStage'
import { imagePreviewUrl } from '../../../types/workbench'

function img(id: string, created: string) {
  return {
    id, job_id: 'job_1', kind: 'original', file_path: `/tmp/${id}.png`,
    width: 800, height: 600, seed: 1, favorite: false, status: 'NEW',
    created_at: created, updated_at: created,
  }
}

const images = [img('img_a', '2026-01-01T00:00:00'), img('img_b', '2026-01-01T00:01:00')]

function completedJob() {
  return {
    id: 'job_1', status: 'COMPLETED', completed_count: 2, positive_prompt_snapshot: 'p',
    module_id: 'basic_generate', stages: [{ completed_count: 2 }],
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUseJobStore.mockReturnValue({
    trackedJob: completedJob(),
    queue: { running: null, queued: [], paused: [] },
    liveProgressByStageItem: {},
  })
})

function renderStage(extra?: ReactNode) {
  return render(
    <MemoryRouter>
      {extra}
      <CanvasStage />
    </MemoryRouter>,
  )
}

async function expectMainSrc(container: HTMLElement, expected: string): Promise<void> {
  await waitFor(() => {
    const el = container.querySelector('[data-testid="canvas-viewport"] img')
    expect(el?.getAttribute('src')).toBe(expected)
  })
}

describe('CanvasStage 键盘切换', () => {
  it('默认显示最后一张；按 ← 切到上一张', async () => {
    const { container } = renderStage()
    await expectMainSrc(container, imagePreviewUrl('img_b'))

    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    await expectMainSrc(container, imagePreviewUrl('img_a'))
  })

  it('在最后一张按 → 循环到第一张', async () => {
    const { container } = renderStage()
    await expectMainSrc(container, imagePreviewUrl('img_b'))

    fireEvent.keyDown(window, { key: 'ArrowRight' })
    await expectMainSrc(container, imagePreviewUrl('img_a'))
  })

  it('输入框聚焦时不拦截方向键（不切换图片）', async () => {
    const { container } = renderStage(<input data-testid="probe" />)
    await expectMainSrc(container, imagePreviewUrl('img_b'))

    fireEvent.keyDown(container.querySelector('[data-testid="probe"]')!, { key: 'ArrowLeft' })
    await new Promise((resolve) => setTimeout(resolve, 50))
    await expectMainSrc(container, imagePreviewUrl('img_b'))
  })
})
