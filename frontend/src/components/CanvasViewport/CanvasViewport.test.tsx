import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import CanvasViewport, {
  clampPan,
  clampScale,
  fitTransform,
  fullSizeTransform,
  wheelFactor,
  zoomAtCursor,
} from './CanvasViewport'
import type { ViewTransform } from './geometry'

const CONTAINER = { width: 800, height: 600 }
const IMAGE = { width: 1024, height: 768 }
const LARGE = { width: 2000, height: 1500 } // 大于容器，平移边界才有意义

let roCallback: ((entries: { contentRect: { width: number; height: number } }[]) => void) | null = null

beforeEach(() => {
  roCallback = null
  class MockResizeObserver {
    constructor(cb: typeof roCallback) {
      roCallback = cb
    }
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  global.ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function renderViewport(props: Partial<Parameters<typeof CanvasViewport>[0]> = {}) {
  return render(
    <CanvasViewport
      imageUrl="a.png"
      imageWidth={IMAGE.width}
      imageHeight={IMAGE.height}
      {...props}
    />,
  )
}

function stage(): HTMLElement {
  return screen.getByTestId('canvas-viewport-canvas')
}

function previewImg(): HTMLImageElement {
  return stage().querySelector('.canvas-viewport__preview') as HTMLImageElement
}

function transformOf(): ViewTransform {
  const style = previewImg().style.transform
  const m = /translate\(([-\d.]+)px,\s*([-\d.]+)px\)\s*scale\(([-\d.]+)\)/.exec(style)
  if (!m) throw new Error(`unexpected transform: ${style}`)
  return { tx: Number(m[1]), ty: Number(m[2]), scale: Number(m[3]) }
}

function wheel(deltaY: number, x = 400, y = 300): void {
  act(() => {
    const e = new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY, clientX: x, clientY: y })
    stage().dispatchEvent(e)
  })
}

describe('CanvasViewport 纯几何', () => {
  it('fitTransform 等比缩放居中', () => {
    const t = fitTransform(CONTAINER, IMAGE)
    expect(t.scale).toBeCloseTo(0.65625, 5)
    expect(t.tx).toBeCloseTo(64, 4)
    expect(t.ty).toBeCloseTo(48, 4)
  })
  it('clampScale 钳制与非法值回落', () => {
    expect(clampScale(99)).toBe(8)
    expect(clampScale(0.0001)).toBe(0.05)
    expect(clampScale(Number.NaN)).toBe(0.05)
  })
  it('wheelFactor 上滚放大下滚缩小', () => {
    expect(wheelFactor(-100)).toBeGreaterThan(1)
    expect(wheelFactor(100)).toBeLessThan(1)
  })
  it('zoomAtCursor 锚点不变量 + 上限', () => {
    const start = fitTransform(CONTAINER, IMAGE)
    const next = zoomAtCursor(start, { x: 400, y: 300 }, 1.5)
    const cx = (400 - start.tx) / start.scale
    const cy = (300 - start.ty) / start.scale
    expect(cx * next.scale + next.tx).toBeCloseTo(400, 4)
    expect(cy * next.scale + next.ty).toBeCloseTo(300, 4)
    expect(zoomAtCursor({ scale: 8, tx: 0, ty: 0 }, { x: 1, y: 1 }, 3).scale).toBe(8)
  })
  it('fullSizeTransform scale=1 居中', () => {
    const t = fullSizeTransform(CONTAINER, IMAGE)
    expect(t.scale).toBe(1)
    expect(t.tx).toBeCloseTo((800 - 1024) / 2, 4)
  })
  it('clampPan：大图不能完全拖出，至少留边缘可回抓；小图锁定居中', () => {
    // 大图放大到 scale=1（2000x1500 > 800x600），向右拖 9999 被钳制
    const clamped = clampPan({ scale: 1, tx: 9999, ty: 9999 }, CONTAINER, LARGE)
    expect(clamped.tx).toBe(40) // edgeGrab
    expect(clamped.ty).toBe(40)
    // 向左拖 -9999 被钳制到 容器宽 - edgeGrab - 图宽
    const clamped2 = clampPan({ scale: 1, tx: -9999, ty: -9999 }, CONTAINER, LARGE)
    expect(clamped2.tx).toBe(800 - 40 - 2000)
    expect(clamped2.ty).toBe(600 - 40 - 1500)
    // 小图（fit 后比容器窄）锁回居中
    const fit = fitTransform(CONTAINER, IMAGE)
    const small = clampPan({ ...fit, tx: 0, ty: 0 }, CONTAINER, IMAGE)
    expect(small.tx).toBeCloseTo((800 - IMAGE.width * fit.scale) / 2, 4)
  })
})

describe('CanvasViewport 组件状态机（Task 5）', () => {
  it('初始即 fit', () => {
    renderViewport()
    const t = transformOf()
    const expectT = fitTransform(CONTAINER, IMAGE)
    expect(t.scale).toBeCloseTo(expectT.scale, 4)
  })

  it('wheel：preventDefault（不滚页面）且以光标为锚放大', () => {
    renderViewport()
    const before = transformOf().scale
    let defaultPrevented = false
    const node = stage()
    node.addEventListener('wheel', (e) => {
      defaultPrevented = e.defaultPrevented
    })
    wheel(-200)
    expect(defaultPrevented).toBe(true)
    expect(transformOf().scale).toBeGreaterThan(before)
  })

  it('pointer drag：平移生效且被边界钳制（不把图拖出）', () => {
    renderViewport({ imageWidth: LARGE.width, imageHeight: LARGE.height })
    // 放大到 scale=1 才能平移（fit 小图锁居中）
    fireEvent.click(screen.getByRole('button', { name: '100%' }))
    fireEvent.pointerDown(stage(), { clientX: 100, clientY: 100, pointerId: 1 })
    fireEvent.pointerMove(stage(), { clientX: 9999, clientY: 9999, pointerId: 1 })
    fireEvent.pointerUp(stage(), { clientX: 9999, clientY: 9999, pointerId: 1 })
    expect(transformOf().tx).toBe(40)
    expect(transformOf().ty).toBe(40)
  })

  it('双击在 Fit / 100% 间切换', () => {
    renderViewport()
    fireEvent.doubleClick(stage())
    expect(transformOf().scale).toBeCloseTo(1, 4)
    fireEvent.doubleClick(stage())
    expect(transformOf().scale).toBeCloseTo(fitTransform(CONTAINER, IMAGE).scale, 4)
  })

  it('切图：transform 重置为 fit', () => {
    const utils = renderViewport()
    fireEvent.doubleClick(stage())
    expect(transformOf().scale).toBeCloseTo(1, 4)
    utils.rerender(<CanvasViewport imageUrl="b.png" imageWidth={IMAGE.width} imageHeight={IMAGE.height} />)
    expect(transformOf().scale).toBeCloseTo(fitTransform(CONTAINER, IMAGE).scale, 4)
  })

  it('ResizeObserver：Fit 模式容器变化自动重新 fit', () => {
    renderViewport()
    act(() => {
      roCallback?.([{ contentRect: { width: 1000, height: 800 } }])
    })
    const t = transformOf()
    expect(t.scale).toBeCloseTo(fitTransform({ width: 1000, height: 800 }, IMAGE).scale, 4)
  })

  it('侧栏拖拽导致容器变化：手动缩放后保持视图中心、不 reset', () => {
    renderViewport()
    wheel(-400, 400, 300) // 手动放大，manual=true
    const before = transformOf()
    const manualScale = before.scale
    expect(manualScale).toBeGreaterThan(fitTransform(CONTAINER, IMAGE).scale)
    // 旧视图中心（400,300）对应的内容点
    const contentX = (400 - before.tx) / before.scale
    const contentY = (300 - before.ty) / before.scale
    act(() => {
      roCallback?.([{ contentRect: { width: 640, height: 600 } }]) // 左栏变宽，Canvas 变窄
    })
    const t = transformOf()
    expect(t.scale).toBeCloseTo(manualScale, 4) // 不被重置回 fit
    // 同一内容点仍映射到新中心（320,300）
    expect(contentX * t.scale + t.tx).toBeCloseTo(320, 0)
    expect(contentY * t.scale + t.ty).toBeCloseTo(300, 0)
  })

  it('preview→original 分层：scale<1 只加载 preview，到 100% 才异步加载 content', () => {
    renderViewport({ imageUrl: 'a-preview.png', contentUrl: 'a-content.png' })
    expect(stage().querySelector('.canvas-viewport__content')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '100%' }))
    const content = stage().querySelector('.canvas-viewport__content') as HTMLImageElement
    expect(content).not.toBeNull()
    expect(content.getAttribute('src')).toBe('a-content.png')
    // 原图未加载完成时透明，保持 preview，不闪白
    expect(content.style.opacity).toBe('0')
    fireEvent.load(content)
    expect(content.style.opacity).toBe('1')
  })

  it('filmstrip wheel 隔离：仅视口容器的 wheel 触发缩放，外部 wheel 不影响', () => {
    renderViewport()
    const before = transformOf().scale
    act(() => {
      const outside = new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: -400 })
      document.body.dispatchEvent(outside)
    })
    expect(transformOf().scale).toBeCloseTo(before, 5)
  })
})
