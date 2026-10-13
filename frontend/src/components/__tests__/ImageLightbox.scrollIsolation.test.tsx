/**
 * ImageLightbox.scrollIsolation（Task 9 / 任务书 §十六 验收路径）：
 * - 打开 Lightbox 时真正的滚动容器 .app-shell__main 被锁（不只锁 body）；
 * - 打开后在 stage 上滚轮缩放，底层 main.scrollTop 保持不动；
 * - 关闭 Lightbox 后页面仍停在原滚动位置。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, fireEvent } from '@testing-library/react'
import { ImageLightbox } from '../ImageLightbox'
import type { ImageDTO } from '../../types/workbench'

const images: Pick<ImageDTO, 'id' | 'width' | 'height' | 'kind'>[] = [
  { id: 'img_a', width: 800, height: 600, kind: 'original' },
  { id: 'img_b', width: 640, height: 640, kind: 'original' },
]

function getMain(): HTMLElement {
  return document.querySelector<HTMLElement>('.app-shell__main') as HTMLElement
}

beforeEach(() => {
  const main = document.createElement('div')
  main.className = 'app-shell__main'
  document.body.appendChild(main)
  document.documentElement.style.overflow = ''
  document.body.style.overflow = ''
  main.style.overflow = ''
  main.scrollTop = 0
})

afterEach(() => {
  cleanup()
  document.querySelector('.app-shell__main')?.remove()
})

describe('ImageLightbox 滚动隔离', () => {
  it('打开后 .app-shell__main 被锁（不只是 body）', () => {
    render(
      <ImageLightbox images={images} index={0} onClose={vi.fn()} onNavigate={vi.fn()} />,
    )
    expect(document.body.style.overflow).toBe('hidden')
    expect(getMain().style.overflow).toBe('hidden')
  })

  it('底层先滚到 500，打开后滚轮 10 次缩放，main.scrollTop 仍为 500', () => {
    getMain().scrollTop = 500
    const { container, unmount } = render(
      <ImageLightbox images={images} index={0} onClose={vi.fn()} onNavigate={vi.fn()} />,
    )
    expect(getMain().scrollTop).toBe(500)

    const stage = container.querySelector('.lb-stage') as HTMLElement
    const img = container.querySelector('.lb-img') as HTMLImageElement
    const before = img.style.transform

    for (let i = 0; i < 10; i += 1) {
      fireEvent.wheel(stage, { deltaY: -100 })
    }

    // 缩放确实发生
    expect(img.style.transform).not.toBe(before)
    expect(img.style.transform).toMatch(/scale\(/)
    // 但底层滚动位置纹丝不动
    expect(getMain().scrollTop).toBe(500)

    // 关闭后仍停在 500
    unmount()
    expect(getMain().scrollTop).toBe(500)
    expect(getMain().style.overflow).toBe('')
  })
})
