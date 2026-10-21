import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const ui3Css = readFileSync(resolve(process.cwd(), 'src/components/ui/ui3/ui3.css'), 'utf8')
const appCss = readFileSync(resolve(process.cwd(), 'src/app/app.css'), 'utf8')

function rule(css: string, selector: string): string {
  const escaped = selector
    .trim()
    .split(/\s+/)
    .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .join('\\s*')
  const match = css.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`))
  expect(match, `缺少 CSS 规则：${selector}`).not.toBeNull()
  return match![1]
}

describe('Tooltip 横向溢出防护', () => {
  it('限制全局 ui3 tooltip 宽度并允许长文案换行', () => {
    const body = rule(ui3Css, '.ui3-tooltip')

    expect(body).toMatch(/max-width\s*:\s*min\(260px,\s*calc\(100vw\s*-\s*32px\)\)\s*;/)
    expect(body).toMatch(/white-space\s*:\s*normal\s*;/)
    expect(body).not.toMatch(/white-space\s*:\s*nowrap\s*;/)
  })

  it('将 TopNav 右侧的 top 和 bottom tooltip 锚定到右边缘', () => {
    const selector =
      '.topnav__right .ui3-tooltip--top, .topnav__right .ui3-tooltip--bottom'
    const body = rule(ui3Css, selector)

    expect(body).toMatch(/left\s*:\s*auto\s*;/)
    expect(body).toMatch(/right\s*:\s*0\s*;/)
    expect(body).toMatch(/transform\s*:\s*none\s*;/)
  })

  it('在 app shell 边界裁剪意外的横向溢出', () => {
    const body = rule(appCss, '.app-shell')

    expect(body).toMatch(/overflow-x\s*:\s*clip\s*;/)
  })
})
