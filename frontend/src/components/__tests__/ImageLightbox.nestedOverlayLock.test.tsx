/**
 * ImageLightbox.nestedOverlayLock（Task 9 / §14.2）：
 * - Lightbox 打开占一个滚动锁；
 * - Lightbox 内再开一个嵌套 overlay（如信息栏里的 Confirm）靠 ref-count 再加一；
 * - 关闭内层后外层锁仍在（overflow 仍 hidden），只有外层也关了才恢复。
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import { ImageLightbox } from '../ImageLightbox'
import { __overlayLockCount, useOverlayScrollLock } from '../../hooks/useOverlayScrollLock'
import type { ImageDTO } from '../../types/workbench'

const images: Pick<ImageDTO, 'id' | 'width' | 'height' | 'kind'>[] = [
  { id: 'img_a', width: 800, height: 600, kind: 'original' },
]

/** 模拟 Lightbox 内再弹出的 Confirm 等内层 overlay。 */
function InnerOverlay(): null {
  useOverlayScrollLock(true)
  return null
}

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
})

afterEach(() => {
  cleanup()
  document.querySelector('.app-shell__main')?.remove()
})

describe('ImageLightbox 嵌套 overlay 滚动锁 ref-count', () => {
  it('内层 overlay 关闭不提前解除外层 Lightbox 锁', () => {
    const outer = render(
      <ImageLightbox images={images} index={0} onClose={() => {}} onNavigate={() => {}} />,
    )
    expect(__overlayLockCount()).toBe(1)
    expect(getMain().style.overflow).toBe('hidden')

    // Lightbox 内再开一个嵌套 overlay（ref-count → 2）
    const inner = render(<InnerOverlay />)
    expect(__overlayLockCount()).toBe(2)
    expect(getMain().style.overflow).toBe('hidden')

    // 内层关闭：外层锁仍在
    inner.unmount()
    expect(__overlayLockCount()).toBe(1)
    expect(document.documentElement.style.overflow).toBe('hidden')
    expect(getMain().style.overflow).toBe('hidden')

    // 外层 Lightbox 关闭：计数归 0，恢复
    outer.unmount()
    expect(__overlayLockCount()).toBe(0)
    expect(document.documentElement.style.overflow).toBe('')
    expect(getMain().style.overflow).toBe('')
  })
})
