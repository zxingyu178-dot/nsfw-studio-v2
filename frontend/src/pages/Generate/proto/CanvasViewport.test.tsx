import { describe, expect, it } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import CanvasViewport, {
  clampScale,
  fitTransform,
  fullSizeTransform,
  wheelFactor,
  zoomAtCursor,
} from './CanvasViewport'

// 固定容器/图尺寸（jsdom 无真实布局，组件回退到 props 占位 800x600 / 图 1024x768）
const CONTAINER = { width: 800, height: 600 }
const IMAGE = { width: 1024, height: 768 }

function renderViewport(url = 'a.png') {
  return render(
    <CanvasViewport imageUrl={url} imageWidth={IMAGE.width} imageHeight={IMAGE.height} />,
  )
}

function stage(): HTMLElement {
  return screen.getByTestId('canvas-viewport-canvas')
}

function transformOf(): { scale: number; tx: number; ty: number } {
  const img = stage().querySelector('img') as HTMLImageElement
  const style = img.style.transform
  // 形如 translate(64px, 48px) scale(0.65625)
  const m = /translate\(([-\d.]+)px,\s*([-\d.]+)px\)\s*scale\(([-\d.]+)\)/.exec(style)
  if (!m) throw new Error(`unexpected transform: ${style}`)
  return { tx: Number(m[1]), ty: Number(m[2]), scale: Number(m[3]) }
}

describe('CanvasViewport 纯几何', () => {
  it('fitTransform：等比缩放到容器内并居中', () => {
    const t = fitTransform(CONTAINER, IMAGE)
    // availW=800*0.84=672, availH=600*0.84=504 -> min(672/1024, 504/768)=0.65625
    expect(t.scale).toBeCloseTo(0.65625, 5)
    expect(t.tx).toBeCloseTo((800 - 1024 * 0.65625) / 2, 5) // 64
    expect(t.ty).toBeCloseTo((600 - 768 * 0.65625) / 2, 5) // 48
  })

  it('clampScale：超出范围被钳制，非法值回落最小值', () => {
    expect(clampScale(99)).toBe(8)
    expect(clampScale(0.0001)).toBe(0.05)
    expect(clampScale(Number.NaN)).toBe(0.05)
  })

  it('wheelFactor：上滚放大、下滚缩小', () => {
    expect(wheelFactor(-100)).toBeGreaterThan(1)
    expect(wheelFactor(100)).toBeLessThan(1)
  })

  it('zoomAtCursor：光标下内容点在缩放后保持原位（锚点不变量）', () => {
    const start = fitTransform(CONTAINER, IMAGE)
    const cursor = { x: 400, y: 300 }
    const next = zoomAtCursor(start, cursor, 1.5)
    // 光标下的内容坐标
    const contentX = (cursor.x - start.tx) / start.scale
    const contentY = (cursor.y - start.ty) / start.scale
    // 缩放后该内容点应仍映射到光标
    expect(contentX * next.scale + next.tx).toBeCloseTo(cursor.x, 5)
    expect(contentY * next.scale + next.ty).toBeCloseTo(cursor.y, 5)
    // scale 被放大
    expect(next.scale).toBeCloseTo(start.scale * 1.5, 5)
  })

  it('zoomAtCursor：命中 scale 上限时不越界', () => {
    const start = { scale: 8, tx: 0, ty: 0 }
    const next = zoomAtCursor(start, { x: 100, y: 100 }, 3)
    expect(next.scale).toBe(8)
  })

  it('fullSizeTransform：scale=1 并居中', () => {
    const t = fullSizeTransform(CONTAINER, IMAGE)
    expect(t.scale).toBe(1)
    expect(t.tx).toBeCloseTo((800 - 1024) / 2, 5)
    expect(t.ty).toBeCloseTo((600 - 768) / 2, 5)
  })
})

describe('CanvasViewport 组件状态机', () => {
  it('初始即 fit：scale/translate 与 fitTransform 一致', () => {
    renderViewport()
    const t = transformOf()
    const expectT = fitTransform(CONTAINER, IMAGE)
    expect(t.scale).toBeCloseTo(expectT.scale, 4)
    expect(t.tx).toBeCloseTo(expectT.tx, 4)
    expect(t.ty).toBeCloseTo(expectT.ty, 4)
  })

  it('pointer drag：平移改变 tx/ty，且 delta 等于指针位移', () => {
    renderViewport()
    const before = transformOf()
    fireEvent.pointerDown(stage(), { clientX: 100, clientY: 100, pointerId: 1 })
    fireEvent.pointerMove(stage(), { clientX: 160, clientY: 140, pointerId: 1 })
    const after = transformOf()
    expect(after.tx).toBeCloseTo(before.tx + 60, 4)
    expect(after.ty).toBeCloseTo(before.ty + 40, 4)
    fireEvent.pointerUp(stage(), { clientX: 160, clientY: 140, pointerId: 1 })
  })

  it('wheel：调用 preventDefault（不滚页面）且以光标为锚放大', () => {
    renderViewport()
    const before = transformOf()
    let wheel: WheelEvent
    // 直接派发到容器（listener 以 { passive:false } 注册）；包 act 以刷新 React 状态
    act(() => {
      wheel = new WheelEvent('wheel', {
        bubbles: true,
        cancelable: true,
        deltaY: -200, // 上滚 = 放大
        clientX: 400,
        clientY: 300,
      })
      stage().dispatchEvent(wheel)
    })
    // cancelable + 我们 preventDefault → defaultPrevented 为 true
    expect(wheel!.defaultPrevented).toBe(true)
    const after = transformOf()
    expect(after.scale).toBeGreaterThan(before.scale)
  })

  it('100% 按钮切换：scale 变为 1，再点回到 fit', () => {
    renderViewport()
    fireEvent.click(screen.getByRole('button', { name: '100%' }))
    expect(transformOf().scale).toBeCloseTo(1, 4)
    fireEvent.click(screen.getByRole('button', { name: '适应' }))
    expect(transformOf().scale).toBeCloseTo(fitTransform(CONTAINER, IMAGE).scale, 4)
  })

  it('适应窗口按钮：把平移后的视口重置回 fit 居中', () => {
    renderViewport()
    fireEvent.pointerDown(stage(), { clientX: 100, clientY: 100, pointerId: 1 })
    fireEvent.pointerMove(stage(), { clientX: 250, clientY: 250, pointerId: 1 })
    fireEvent.pointerUp(stage(), { clientX: 250, clientY: 250, pointerId: 1 })
    // 平移已生效
    expect(transformOf().tx).not.toBeCloseTo(fitTransform(CONTAINER, IMAGE).tx, 1)
    fireEvent.click(screen.getByRole('button', { name: '适应窗口' }))
    const t = transformOf()
    expect(t.tx).toBeCloseTo(fitTransform(CONTAINER, IMAGE).tx, 4)
    expect(t.ty).toBeCloseTo(fitTransform(CONTAINER, IMAGE).ty, 4)
  })

  it('切换图片：transform 自动重置为 fit（不残留旧平移/缩放）', () => {
    const utils = renderViewport('a.png')
    // 先平移 + 放大
    fireEvent.pointerDown(stage(), { clientX: 100, clientY: 100, pointerId: 1 })
    fireEvent.pointerMove(stage(), { clientX: 300, clientY: 300, pointerId: 1 })
    fireEvent.pointerUp(stage(), { clientX: 300, clientY: 300, pointerId: 1 })
    expect(transformOf().tx).not.toBeCloseTo(fitTransform(CONTAINER, IMAGE).tx, 1)
    // 切图
    utils.rerender(
      <CanvasViewport imageUrl="b.png" imageWidth={IMAGE.width} imageHeight={IMAGE.height} />,
    )
    const t = transformOf()
    expect(t.tx).toBeCloseTo(fitTransform(CONTAINER, IMAGE).tx, 4)
    expect(t.ty).toBeCloseTo(fitTransform(CONTAINER, IMAGE).ty, 4)
    expect(t.scale).toBeCloseTo(fitTransform(CONTAINER, IMAGE).scale, 4)
  })
})
