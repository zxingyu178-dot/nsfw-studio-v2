import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ImageLightbox } from '../ImageLightbox'
import type { ImageDTO } from '../../types/workbench'

const images: Pick<ImageDTO, 'id' | 'width' | 'height' | 'kind'>[] = [
  { id: 'img_a', width: 800, height: 600, kind: 'original' },
  { id: 'img_b', width: 640, height: 640, kind: 'original' },
  { id: 'img_c', width: 1024, height: 768, kind: 'upscaled' },
]

function renderAt(index: number, onNavigate = vi.fn()) {
  const onClose = vi.fn()
  const utils = render(
    <ImageLightbox images={images} index={index} onClose={onClose} onNavigate={onNavigate} />
  )
  return { ...utils, onClose, onNavigate }
}

describe('ImageLightbox 共享看图 Lightbox', () => {
  it('打开时只渲染当前这一张的 preview URL，不批量预载其余原图', () => {
    const { container } = renderAt(0)
    const imgs = container.querySelectorAll('img')
    expect(imgs).toHaveLength(1)
    // 渐进加载：默认 preview（长边 1536），不是完整 original
    expect(imgs[0].getAttribute('src')).toBe('/api/v1/images/img_a/preview')
    // 其余两张的原图 URL 不得出现在 DOM 中（无批量请求）
    expect(container.innerHTML).not.toContain('/api/v1/images/img_b/content')
    expect(container.innerHTML).not.toContain('/api/v1/images/img_c/content')
  })

  it('ESC 触发 onClose', () => {
    const { onClose } = renderAt(0)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('← / → 切换 index 并加载对应图（不预载，按需渲染）', () => {
    const utils = renderAt(0)
    fireEvent.keyDown(document, { key: 'ArrowRight' })
    expect(utils.onNavigate).toHaveBeenCalledWith(1)

    // 父组件把 index 切到 1 后，src 换成 img_b；此时仍只有一张图
    utils.rerender(
      <ImageLightbox images={images} index={1} onClose={vi.fn()} onNavigate={utils.onNavigate} />
    )
    const imgs = utils.container.querySelectorAll('img')
    expect(imgs).toHaveLength(1)
    expect(imgs[0].getAttribute('src')).toBe('/api/v1/images/img_b/preview')
    expect(utils.container.innerHTML).not.toContain('/api/v1/images/img_c/content')

    fireEvent.keyDown(document, { key: 'ArrowLeft' })
    expect(utils.onNavigate).toHaveBeenCalledWith(0)
  })

  it('滚轮缩放使 transform/scale 变化', () => {
    const { container } = renderAt(0)
    const stage = container.querySelector('.lb-stage') as HTMLElement
    const img = container.querySelector('.lb-img') as HTMLImageElement
    // 初始 = 适应窗口，无 transform
    expect(img.style.transform).toBe('')
    fireEvent.wheel(stage, { deltaY: -100 })
    expect(img.style.transform).not.toBe('')
    expect(img.style.transform).toMatch(/scale\(1\.2\)/)
  })

  it('Fit 复位（清除 transform），100% 设为 scale=1', () => {
    const { container } = renderAt(0)
    const stage = container.querySelector('.lb-stage') as HTMLElement
    const img = container.querySelector('.lb-img') as HTMLImageElement

    fireEvent.wheel(stage, { deltaY: -100 })
    expect(img.style.transform).not.toBe('')

    fireEvent.click(screen.getByRole('button', { name: '适应窗口' }))
    expect(img.style.transform).toBe('')

    fireEvent.click(screen.getByRole('button', { name: '100%' }))
    expect(img.style.transform).toMatch(/scale\(1\)/)
  })

  it('缩放被 clamp 在 0.25~4', () => {
    const { container } = renderAt(0)
    const stage = container.querySelector('.lb-stage') as HTMLElement
    const img = container.querySelector('.lb-img') as HTMLImageElement

    // 疯狂放大 → 不超过 4
    for (let i = 0; i < 20; i += 1) fireEvent.wheel(stage, { deltaY: -100 })
    const upMatch = img.style.transform.match(/scale\(([\d.]+)\)/)
    expect(upMatch).not.toBeNull()
    expect(Number(upMatch![1])).toBeLessThanOrEqual(4)
    expect(Number(upMatch![1])).toBe(4)

    // 复位后疯狂缩小 → 不低于 0.25
    fireEvent.click(screen.getByRole('button', { name: '适应窗口' }))
    for (let i = 0; i < 30; i += 1) fireEvent.wheel(stage, { deltaY: 100 })
    const downMatch = img.style.transform.match(/scale\(([\d.]+)\)/)
    expect(Number(downMatch![1])).toBeGreaterThanOrEqual(0.25)
    expect(Number(downMatch![1])).toBe(0.25)
  })

  it('拖动平移改变 offset（缩放后）', () => {
    const { container } = renderAt(0)
    const img = container.querySelector('.lb-img') as HTMLImageElement
    fireEvent.click(screen.getByRole('button', { name: '100%' }))
    expect(img.style.transform).toMatch(/translate\(0px, 0px\)/)

    fireEvent.mouseDown(img, { clientX: 0, clientY: 0 })
    fireEvent.mouseMove(window, { clientX: 60, clientY: 30 })
    fireEvent.mouseUp(window)
    expect(img.style.transform).toMatch(/translate\(60px, 30px\)/)
  })

  it('切换图片后缩放/平移复位', () => {
    const { container, rerender } = renderAt(0)
    const stage = container.querySelector('.lb-stage') as HTMLElement
    const img = container.querySelector('.lb-img') as HTMLImageElement
    fireEvent.wheel(stage, { deltaY: -100 })
    fireEvent.mouseDown(img, { clientX: 0, clientY: 0 })
    fireEvent.mouseMove(window, { clientX: 40, clientY: 20 })
    fireEvent.mouseUp(window)
    expect(img.style.transform).not.toBe('')

    rerender(
      <ImageLightbox images={images} index={1} onClose={vi.fn()} onNavigate={vi.fn()} />
    )
    const img2 = container.querySelector('.lb-img') as HTMLImageElement
    // 切图后缩放复位 → 回到 preview
    expect(img2.getAttribute('src')).toBe('/api/v1/images/img_b/preview')
    expect(img2.style.transform).toBe('')

    // 点 100% → 切换为 original content
    fireEvent.click(screen.getByRole('button', { name: '100%' }))
    expect(container.querySelector('.lb-img')?.getAttribute('src')).toBe('/api/v1/images/img_b/content')
  })

  it('hasMore/onLoadMore：到末尾按下一张触发加载更多而非禁用', () => {
    const onLoadMore = vi.fn()
    render(
      <ImageLightbox images={images} index={2} onClose={vi.fn()} onNavigate={vi.fn()} hasMore onLoadMore={onLoadMore} />
    )
    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))
    expect(onLoadMore).toHaveBeenCalledTimes(1)
  })
})
