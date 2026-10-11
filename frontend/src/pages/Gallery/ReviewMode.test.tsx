import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { imageApi } from '../../api/client'
import { ReviewMode } from './ReviewMode'
import type { ImageDTO } from '../../types/workbench'

vi.mock('../../api/client', () => ({
  ApiRequestError: class extends Error {},
  imageApi: {
    setStatus: vi.fn(),
  },
}))

function makeImage(id: string, status: ImageDTO['status'] = 'NEW'): ImageDTO {
  return {
    id,
    job_id: 'job_1',
    job_item_id: null,
    parent_image_id: null,
    kind: 'original',
    file_path: `originals/${id}.png`,
    width: 800,
    height: 600,
    seed: 1,
    review_status: 'UNREVIEWED',
    favorite: false,
    status,
    source: 'comfyui',
    metadata: {},
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00',
  }
}

const images = [makeImage('img_a'), makeImage('img_b'), makeImage('img_c')]

function renderMode() {
  return render(
    <MemoryRouter>
      <ReviewMode images={images} onClose={() => {}} onChanged={() => {}} />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  // setStatus 返回打标后的图
  vi.mocked(imageApi.setStatus).mockImplementation((id, body) =>
    Promise.resolve({ ...images.find((i) => i.id === id)!, status: body.status } as ImageDTO),
  )
})

describe('ReviewMode 审核选片', () => {
  it('显示进度与统计，大图载 original content', () => {
    const { container } = renderMode()
    expect(screen.getByText('1 / 3')).toBeInTheDocument()
    const img = container.querySelector('.rv-img') as HTMLImageElement
    expect(img.getAttribute('src')).toBe('/api/v1/images/img_a/content')
  })

  it('点「保留」调用 setStatus(KEEP) 并自动跳到下一张', async () => {
    renderMode()
    fireEvent.click(screen.getByRole('button', { name: /保留/ }))
    await waitFor(() => expect(imageApi.setStatus).toHaveBeenCalledWith('img_a', { status: 'KEEP' }))
    // 自动前进
    expect(await screen.findByText('2 / 3')).toBeInTheDocument()
  })

  it('「收藏」「淘汰」按钮分别打标 FAVORITE / REJECT', async () => {
    renderMode()
    fireEvent.click(screen.getByRole('button', { name: /淘汰/ }))
    await waitFor(() => expect(imageApi.setStatus).toHaveBeenCalledWith('img_a', { status: 'REJECT' }))
    fireEvent.click(screen.getByRole('button', { name: /收藏/ }))
    await waitFor(() => expect(imageApi.setStatus).toHaveBeenCalledWith('img_b', { status: 'FAVORITE' }))
  })
})

describe('KeyboardReview 快捷键', () => {
  it('方向键切换；A 保留 / D 淘汰 / F 收藏；Space 放大', async () => {
    const { container } = renderMode()
    expect(screen.getByText('1 / 3')).toBeInTheDocument()

    // → 下一张
    fireEvent.keyDown(document, { key: 'ArrowRight' })
    expect(screen.getByText('2 / 3')).toBeInTheDocument()
    // ← 上一张
    fireEvent.keyDown(document, { key: 'ArrowLeft' })
    expect(screen.getByText('1 / 3')).toBeInTheDocument()

    // A = 保留
    fireEvent.keyDown(document, { key: 'a' })
    await waitFor(() => expect(imageApi.setStatus).toHaveBeenCalledWith('img_a', { status: 'KEEP' }))

    // D = 淘汰（当前已前进到 img_b）
    fireEvent.keyDown(document, { key: 'd' })
    await waitFor(() => expect(imageApi.setStatus).toHaveBeenCalledWith('img_b', { status: 'REJECT' }))

    // F = 收藏（前进到 img_c）
    fireEvent.keyDown(document, { key: 'f' })
    await waitFor(() => expect(imageApi.setStatus).toHaveBeenCalledWith('img_c', { status: 'FAVORITE' }))

    // Space 放大：img 进入 zoomed 态
    fireEvent.keyDown(document, { key: ' ' })
    expect(container.querySelector('.rv-img--zoomed')).toBeTruthy()
  })
})
