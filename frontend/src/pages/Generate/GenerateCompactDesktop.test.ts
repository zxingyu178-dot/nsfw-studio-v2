/**
 * Workbench 4.0 响应式断点合同（v0.15）：
 *  ≥1200     可调三栏（像素左/右 + 中间 1fr，手柄可见）
 *  1024–1199 固定紧凑三栏（左 280 / 右 270，隐藏拖拽手柄）
 *  <1024     Workspace Tabs（一次一个 pane，TaskDock 常驻）
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const SRC_DIR = resolve(process.cwd(), 'src')
function readCss(relPath: string): string {
  return readFileSync(resolve(SRC_DIR, relPath), 'utf8')
}

function mediaBlock(css: string, maxWidth: number): string {
  const marker = `@media (max-width: ${maxWidth}px)`
  const start = css.indexOf(marker)
  expect(start, `${maxWidth}px 媒体查询未找到`).toBeGreaterThanOrEqual(0)
  const open = css.indexOf('{', start)
  let depth = 0
  for (let i = open; i < css.length; i++) {
    if (css[i] === '{') depth++
    else if (css[i] === '}') {
      depth--
      if (depth === 0) return css.slice(open + 1, i)
    }
  }
  throw new Error(`${maxWidth}px 媒体查询括号不匹配`)
}

describe('Workbench 4.0 三档断点', () => {
  it('≥1200 默认：三栏用像素宽 + 中间 1fr（flex 行，非旧 grid），手柄可见', () => {
    const css = readCss('pages/Generate/generate.css')
    expect(css).toMatch(/\.wb4-columns\s*\{[^}]*display:\s*flex/)
    expect(css).toMatch(/\.wb4-pane--left\s*\{[^}]*flex:\s*0 0 var\(--left-w/)
    expect(css).toMatch(/\.wb4-center\s*\{[^}]*flex:\s*1 1 auto/)
    // 不应再有旧的 5fr 4fr 3fr grid
    expect(css).not.toMatch(/grid-template-columns:\s*5fr\s+4fr\s+3fr/)
  })

  it('1024–1199 紧凑档：固定左 280 / 右 270，隐藏拖拽手柄', () => {
    const block = mediaBlock(readCss('pages/Generate/generate.css'), 1199)
    expect(block).toMatch(/--left-w:\s*280px/)
    expect(block).toMatch(/--right-w:\s*270px/)
    expect(block).toMatch(/\.wb4-resize-handle\s*\{\s*display:\s*none/)
  })

  it('<1024：Tabs 显示、列纵向堆叠，仅当前 tab 的 pane 可见', () => {
    const block = mediaBlock(readCss('pages/Generate/generate.css'), 1023)
    expect(block).toMatch(/\.generate\s+\.generate__tabs\s*\{\s*display:\s*flex/)
    expect(block).toMatch(/flex-direction:\s*column/)
    expect(block).toMatch(/\.generate--tab-prompt\s+\.wb4-pane--left/)
    expect(block).toMatch(/\.generate--tab-preview\s+\.wb4-center/)
    expect(block).toMatch(/\.generate--tab-settings\s+\.wb4-pane--right/)
  })
})
