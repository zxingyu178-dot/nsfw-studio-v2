/**
 * useOverlayScrollLock —— 通用 Overlay 滚动锁（Phase 0.14 / 任务书 §十四）。
 *
 * 背景：应用真正的纵向滚动容器是 `.app-shell__main`（见 app.css），
 * 只锁 body 挡不住它。打开 overlay 时必须同时锁三层：
 *   html / body / .app-shell__main 的 overflow，并记录 main 的 scrollTop。
 *
 * 嵌套 overlay（Lightbox 内再弹 Confirm）用模块级 ref-count：
 *   - 第一次加锁时快照基线值；
 *   - 每多一个 overlay +1，关闭一个 -1；
 *   - 计数归 0 才恢复加锁前的 overflow / scrollTop。
 * 这样内层 Confirm 关闭不会提前解除外层 Lightbox 的锁。
 *
 * 用法：const locked = true; useOverlayScrollLock(locked)
 */
import { useEffect } from 'react'

interface LayerSnapshot {
  htmlOverflow: string
  bodyOverflow: string
  mainOverflow: string
  mainScrollTop: number
}

let activeCount = 0
let baseline: LayerSnapshot | null = null

function getMainEl(): HTMLElement | null {
  if (typeof document === 'undefined') return null
  return document.querySelector<HTMLElement>('.app-shell__main')
}

function applyLock() {
  if (activeCount === 0) {
    const main = getMainEl()
    baseline = {
      htmlOverflow: document.documentElement.style.overflow,
      bodyOverflow: document.body.style.overflow,
      mainOverflow: main ? main.style.overflow : '',
      mainScrollTop: main ? main.scrollTop : 0,
    }
  }
  activeCount += 1
  document.documentElement.style.overflow = 'hidden'
  document.body.style.overflow = 'hidden'
  const main = getMainEl()
  if (main) main.style.overflow = 'hidden'
}

function releaseLock() {
  activeCount = Math.max(0, activeCount - 1)
  if (activeCount === 0 && baseline) {
    document.documentElement.style.overflow = baseline.htmlOverflow
    document.body.style.overflow = baseline.bodyOverflow
    const main = getMainEl()
    if (main) {
      main.style.overflow = baseline.mainOverflow
      main.scrollTop = baseline.mainScrollTop
    }
    baseline = null
  }
}

/**
 * 当 `locked` 为 true 时锁定页面滚动（html/body/.app-shell__main），
 * 卸载或 `locked` 变 false 时释放；嵌套 overlay 安全。
 */
export function useOverlayScrollLock(locked: boolean): void {
  useEffect(() => {
    if (!locked) return
    applyLock()
    return () => releaseLock()
  }, [locked])
}

/** 仅供测试/调试：当前活跃锁计数。 */
export function __overlayLockCount(): number {
  return activeCount
}
