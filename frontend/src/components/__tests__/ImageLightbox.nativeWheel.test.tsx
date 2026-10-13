/**
 * ImageLightbox.nativeWheel（Task 9 / §14.3）：
 * - .lb-stage 的 wheel 以 { passive: false } 注册（React onWheel 是 passive 委托，拦不住）；
 * - handler 调用 preventDefault（事件 defaultPrevented）与 stopPropagation（不冒泡到 document）。
 * jsdom 无法真实模拟「浏览器把 wheel 当 passive 忽略 preventDefault」，这里用监听注册与调用证据替代。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { ImageLightbox } from '../ImageLightbox'
import type { ImageDTO } from '../../types/workbench'

const images: Pick<ImageDTO, 'id' | 'width' | 'height' | 'kind'>[] = [
  { id: 'img_a', width: 800, height: 600, kind: 'original' },
]

describe('ImageLightbox native non-passive wheel', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('.lb-stage 以 { passive: false } 注册 wheel 监听', () => {
    const wheelRegs: Array<{ target: EventTarget; opts: unknown }> = []
    const origAdd = EventTarget.prototype.addEventListener
    vi.spyOn(EventTarget.prototype, 'addEventListener').mockImplementation(function (
      this: EventTarget,
      type: string,
      listener: EventListenerOrEventListenerObject | null,
      options?: boolean | AddEventListenerOptions,
    ) {
      if (type === 'wheel') wheelRegs.push({ target: this, opts: options })
      return origAdd.call(this, type, listener, options)
    })

    const { container } = render(
      <ImageLightbox images={images} index={0} onClose={() => {}} onNavigate={() => {}} />,
    )
    const stage = container.querySelector('.lb-stage') as HTMLElement

    const reg = wheelRegs.find((r) => r.target === stage)
    expect(reg, '应在 .lb-stage 上注册 wheel 监听').toBeTruthy()
    // 必须是对象形式且 passive:false（传 true 或省略都会被浏览器当 passive）
    expect(reg!.opts).toBeTypeOf('object')
    expect((reg!.opts as AddEventListenerOptions).passive).toBe(false)
  })

  it('handler 调用 preventDefault（事件被取消）', () => {
    const { container } = render(
      <ImageLightbox images={images} index={0} onClose={() => {}} onNavigate={() => {}} />,
    )
    const stage = container.querySelector('.lb-stage') as HTMLElement

    const event = new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: -100 })
    stage.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
  })

  it('handler 调用 stopPropagation（wheel 不冒泡到 document）', () => {
    const { container } = render(
      <ImageLightbox images={images} index={0} onClose={() => {}} onNavigate={() => {}} />,
    )
    const stage = container.querySelector('.lb-stage') as HTMLElement

    const onDocWheel = vi.fn()
    document.addEventListener('wheel', onDocWheel)
    try {
      stage.dispatchEvent(
        new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: -100 }),
      )
    } finally {
      document.removeEventListener('wheel', onDocWheel)
    }
    expect(onDocWheel).not.toHaveBeenCalled()
  })
})
