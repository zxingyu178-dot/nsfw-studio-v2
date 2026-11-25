/**
 * 创作页响应式断点合同：
 *  ≥1200     Prompt 主栏弹性占满 + 参数栏保留既有宽度偏好
 *  1024–1199 紧凑双栏，隐藏拖拽手柄
 *  <1024     Prompt / 参数 Tabs（一次一个 pane，TaskDock 常驻）
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

describe('创作页双栏三档断点', () => {
  it('≥1200 默认：Prompt 栏弹性填满、参数栏使用宽度偏好，无预览列', () => {
    const css = readCss('pages/Generate/generate.css')
    expect(css).toMatch(/\.wb4-columns\s*\{[^}]*display:\s*flex/)
    expect(css).toMatch(/\.generate--creation\s+\.wb4-pane--left\s*\{[^}]*flex:\s*1 1 var\(--left-w/)
    expect(css).toMatch(/\.generate--creation\s+\.wb4-pane--right\s*\{[^}]*flex:\s*0 1 var\(--right-w/)
    expect(css).not.toMatch(/\.generate--tab-preview\s+\.wb4-center/)
    // 不应再有旧的 5fr 4fr 3fr grid
    expect(css).not.toMatch(/grid-template-columns:\s*5fr\s+4fr\s+3fr/)
  })

  it('1024–1199 紧凑档：双栏占满且隐藏拖拽手柄', () => {
    const block = mediaBlock(readCss('pages/Generate/generate.css'), 1199)
    expect(block).toMatch(/\.generate--creation\s+\.wb4-pane--left/)
    expect(block).toMatch(/\.generate--creation\s+\.wb4-pane--right/)
    expect(block).toMatch(/\.wb4-resize-handle\s*\{\s*display:\s*none/)
  })

  it('<1024：双 Tabs 显示、列纵向堆叠，仅当前 tab 的 pane 可见', () => {
    const block = mediaBlock(readCss('pages/Generate/generate.css'), 1023)
    expect(block).toMatch(/\.generate\s+\.generate__tabs\s*\{\s*display:\s*flex/)
    expect(block).toMatch(/flex-direction:\s*column/)
    expect(block).toMatch(/\.generate--tab-prompt\s+\.wb4-pane--left/)
    expect(block).toMatch(/\.generate--tab-settings\s+\.wb4-pane--right/)
  })
})
