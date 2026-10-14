/**
 * Phase 0.13：Generate 工作台“无整页文档滚动”契约
 *
 * 真实浏览器断言（Playwright）在多分辨率下实测 scrollHeight==clientHeight；
 * 本测试从 CSS 源码层面锁定根因修复，防止 1179px 回退再次出现。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const SRC_DIR = resolve(process.cwd(), 'src')
function readCss(relPath: string): string {
  return readFileSync(resolve(SRC_DIR, relPath), 'utf8')
}

describe('GenerateNoDocumentScroll：根级高度锁，禁止整页撑长', () => {
  it('.ds-page--fill 高度 100% + min-height:0 + overflow:hidden（任何宽度都不回退）', () => {
    const css = readCss('components/layout/layout.css')
    const block = css.match(/\.ds-page--fill\s*\{([^}]+)\}/)
    expect(block, '.ds-page--fill 规则块未找到').toBeTruthy()
    const body = block![1]
    expect(body).toMatch(/height\s*:\s*100%/)
    expect(body).toMatch(/min-height\s*:\s*0/)
    expect(body).toMatch(/overflow\s*:\s*hidden/)
  })

  it('layout.css 不得存在 1179px 把 .ds-page--fill 改回 height:auto/display:block 的回退', () => {
    const css = readCss('components/layout/layout.css')
    expect(css).not.toMatch(/max-width\s*:\s*1179\s*px/)
    // 回退特征：height:auto + display:block 作用于 .ds-page--fill
    expect(css).not.toMatch(/\.ds-page--fill\s*\{[^}]*height\s*:\s*auto/)
  })

  it('.generate 根高度锁：height:100% + min-height:0 + overflow:hidden，wb4-columns flex:1/min-height:0 内部滚动', () => {
    const css = readCss('pages/Generate/generate.css')
    const gen = css.match(/\.generate\s*\{([^}]+)\}/)
    expect(gen, '.generate 规则块未找到').toBeTruthy()
    expect(gen![1]).toMatch(/height\s*:\s*100%/)
    expect(gen![1]).toMatch(/min-height\s*:\s*0/)

    const wb4 = css.match(/\.generate\.wb4\s*\{([^}]+)\}/)
    expect(wb4, '.generate.wb4 规则块未找到').toBeTruthy()
    expect(wb4![1]).toMatch(/overflow\s*:\s*hidden/)

    const cols = css.match(/\.wb4-columns\s*\{([^}]+)\}/)
    expect(cols, '.wb4-columns 规则块未找到').toBeTruthy()
    expect(cols![1]).toMatch(/flex\s*:\s*1 1 auto/)
    expect(cols![1]).toMatch(/min-height\s*:\s*0/)
  })

  it('.wb-pane__body 内部滚动（overflow-y:auto），pane 不溢出撑长', () => {
    const css = readCss('pages/Generate/generate.css')
    const body = css.match(/\.wb-pane__body\s*\{([^}]+)\}/)
    expect(body, '.wb-pane__body 规则块未找到').toBeTruthy()
    expect(body![1]).toMatch(/overflow-y\s*:\s*auto/)
  })
})
