import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// 每个用例后自动卸载组件，避免状态泄漏。
afterEach(() => {
  cleanup()
})

// ===== IntersectionObserver 假实现（jsdom 不提供） =====
// Phase 0.11：图库无限滚动 + 图片懒加载均依赖 IO。这里给出一个可控假实现：
// - 默认不自动触发（元素进入视口才算）；
// - 测试通过 (window as any).__triggerIntersection() 模拟"进入视口"。
class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = []
  callback: IntersectionObserverCallback
  options: IntersectionObserverInit
  targets: Set<Element>

  constructor(callback: IntersectionObserverCallback, options: IntersectionObserverInit = {}) {
    this.callback = callback
    this.options = options
    this.targets = new Set()
    FakeIntersectionObserver.instances.push(this)
  }
  observe(target: Element): void {
    this.targets.add(target)
  }
  unobserve(target: Element): void {
    this.targets.delete(target)
  }
  disconnect(): void {
    this.targets.clear()
  }
  takeRecords(): IntersectionObserverEntry[] {
    return []
  }
}

;(globalThis as unknown as { IntersectionObserver: typeof IntersectionObserver }).IntersectionObserver =
  FakeIntersectionObserver as unknown as typeof IntersectionObserver

;(globalThis as unknown as Record<string, unknown>).__triggerIntersection = (
  isIntersecting = true,
): void => {
  for (const inst of FakeIntersectionObserver.instances) {
    for (const target of inst.targets) {
      inst.callback(
        [
          {
            isIntersecting,
            target,
            intersectionRatio: isIntersecting ? 1 : 0,
            boundingClientRect: target.getBoundingClientRect(),
            intersectionRect: {} as DOMRectReadOnly,
            rootBounds: null,
            time: Date.now(),
          } as IntersectionObserverEntry,
        ],
        inst as unknown as IntersectionObserver,
      )
    }
  }
}

afterEach(() => {
  FakeIntersectionObserver.instances = []
})
