import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { imageThumbUrl, shortJobId, type ImageJobGroupDTO } from '../../../types/workbench'
import { formatDateTime } from '../../../utils/format'
import { GalleryGroupView } from './GalleryGroupView'

const group = {
  job_id: 'job_12345678abcdef',
  module_id: 'basic_generate',
  created_at: '2026-10-20T02:30:00Z',
  total: 9,
  unreviewed: 3,
  kept: 2,
  rejected: 1,
  favorites: 4,
  preview_image_ids: ['img_1', 'img_2', 'img_3', 'img_4', 'img_5'],
} as ImageJobGroupDTO

function renderView(overrides: Partial<React.ComponentProps<typeof GalleryGroupView>> = {}) {
  const props: React.ComponentProps<typeof GalleryGroupView> = {
    groups: [group],
    loading: false,
    hasNext: false,
    page: 1,
    onApplyJobFilter: vi.fn(),
    onReviewJob: vi.fn(),
    onLoadMore: vi.fn(),
    ...overrides,
  }
  return { ...render(<GalleryGroupView {...props} />), props }
}

describe('GalleryGroupView', () => {
  it('展示任务摘要、四类计数和最多四张缩略图', () => {
    const { container } = renderView()

    expect(screen.getByText(shortJobId(group.job_id))).toBeInTheDocument()
    expect(container).toHaveTextContent(formatDateTime(group.created_at))
    expect(screen.getByText(group.module_id!)).toBeInTheDocument()
    expect(screen.getByText(/未审核\s*3/)).toBeInTheDocument()
    expect(screen.getByText(/保留\s*2/)).toBeInTheDocument()
    expect(screen.getByText(/收藏\s*4/)).toBeInTheDocument()
    expect(screen.getByText(/淘汰\s*1/)).toBeInTheDocument()

    const thumbnails = container.querySelectorAll<HTMLImageElement>('.gal-group__thumb')
    expect(thumbnails).toHaveLength(4)
    expect([...thumbnails].map((image) => image.src)).toEqual(
      group.preview_image_ids!.slice(0, 4).map((id) => new URL(imageThumbUrl(id), window.location.href).href),
    )
    expect([...thumbnails].every((image) => image.getAttribute('loading') === 'lazy')).toBe(true)
    expect(screen.getByText('+5')).toBeInTheDocument()
  })

  it('点击卡片时应用任务筛选', () => {
    const onApplyJobFilter = vi.fn()
    renderView({ onApplyJobFilter })

    fireEvent.click(screen.getByText(shortJobId(group.job_id)).closest('.gal-group')!)

    expect(onApplyJobFilter).toHaveBeenCalledOnce()
    expect(onApplyJobFilter).toHaveBeenCalledWith(group.job_id)
  })

  it('没有预览图片时展示占位', () => {
    renderView({ groups: [{ ...group, preview_image_ids: undefined }] })

    expect(screen.getByText('暂无预览')).toBeInTheDocument()
  })

  it('点击开始审核只触发审核操作且不冒泡到卡片', () => {
    const onApplyJobFilter = vi.fn()
    const onReviewJob = vi.fn()
    renderView({ onApplyJobFilter, onReviewJob })

    fireEvent.click(screen.getByRole('button', { name: '开始审核' }))

    expect(onReviewJob).toHaveBeenCalledOnce()
    expect(onReviewJob).toHaveBeenCalledWith(group.job_id)
    expect(onApplyJobFilter).not.toHaveBeenCalled()
  })
})
