/**
 * useOverlayScrollLock 测试：
 * - 打开时锁定 html / body / .app-shell__main 三层 overflow；
 * - 关闭时恢复加锁前的 overflow 与 scrollTop；
 * - ref-count 嵌套：内层关闭不解除外层锁，归 0 才恢复。
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import { __overlayLockCount, useOverlayScrollLock } from './useOverlayScrollLock'

function Harness({ locked }: { locked: boolean }) {
  useOverlayScrollLock(locked)
  return <div data-testid="harness" />
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
  main.scrollTop = 0
})

afterEach(() => {
  cleanup()
  document.querySelector('.app-shell__main')?.remove()
})

describe('useOverlayScrollLock', () => {
  it('打开时锁定 html / body / .app-shell__main 三层 overflow', () => {
    render(<Harness locked />)
    expect(document.documentElement.style.overflow).toBe('hidden')
    expect(document.body.style.overflow).toBe('hidden')
    expect(getMain().style.overflow).toBe('hidden')
  })

  it('关闭（卸载）后恢复加锁前的 overflow', () => {
    const { unmount } = render(<Harness locked />)
    expect(document.documentElement.style.overflow).toBe('hidden')
    unmount()
    expect(document.documentElement.style.overflow).toBe('')
    expect(document.body.style.overflow).toBe('')
    expect(getMain().style.overflow).toBe('')
  })

  it('锁定期间记录的 scrollTop 在解锁后恢复到原值', () => {
    getMain().scrollTop = 500
    const { unmount } = render(<Harness locked />)
    // 锁定期间不改变 scrollTop
    expect(getMain().scrollTop).toBe(500)
    unmount()
    expect(getMain().scrollTop).toBe(500)
  })

  it('ref-count 嵌套：内层关闭不解除外层锁，归 0 才恢复', () => {
    const outer = render(<Harness locked />)
    expect(__overlayLockCount()).toBe(1)
    expect(getMain().style.overflow).toBe('hidden')

    // 内层 overlay（如 Confirm）打开
    const inner = render(<Harness locked />)
    expect(__overlayLockCount()).toBe(2)
    expect(getMain().style.overflow).toBe('hidden')

    // 内层关闭：外层锁仍在
    inner.unmount()
    expect(__overlayLockCount()).toBe(1)
    expect(document.documentElement.style.overflow).toBe('hidden')
    expect(getMain().style.overflow).toBe('hidden')

    // 外层关闭：计数归 0，恢复
    outer.unmount()
    expect(__overlayLockCount()).toBe(0)
    expect(document.documentElement.style.overflow).toBe('')
    expect(getMain().style.overflow).toBe('')
  })
})
