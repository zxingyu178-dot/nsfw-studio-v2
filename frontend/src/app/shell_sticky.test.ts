/**
 * Phase 0.13 App Shell / Workspace / Responsive 契约测试
 *
 * 硬约束（后续 agent 不得破坏）：
 * 1. --topnav-height 在 tokens.css 中定义（56px）。
 * 2. z-index 契约：--z-nav > --z-page-sticky（页内浮层永远在一级导航之下）。
 * 3. TopNav 使用 sticky top:0。
 * 4. Workbench 4.0 顶栏（.wb4-bar）非 sticky——工作台根级禁止整页滚动，顶栏为 static + flex-shrink:0。
 * 5. 响应式断点（v0.15）：≥1200 可调三栏；1024~1199 固定紧凑三栏（280/270）；<1024 Workspace Tabs。
 *    任何宽度都不得回退整页文档滚动（不得再出现 1179px / 1319px 旧堆叠回退）。
 * 6. .app-shell__main--workspace overflow:hidden（Generate 路由根级禁止撑长）。
 * 7. .ds-page--fill 高度锁死 + overflow:hidden。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// vitest 从 frontend/ 目录启动，src/ 即 process.cwd()/src。
const SRC_DIR = resolve(process.cwd(), 'src')

function readCss(relPath: string): string {
  // relPath 相对 src/，例如 'themes/tokens.css'。
  return readFileSync(resolve(SRC_DIR, relPath), 'utf8')
}

function tokenValue(css: string, name: string): string | null {
  const re = new RegExp(`--${name.replace(/^--/, '')}\\s*:\\s*([^;]+);`)
  const m = css.match(re)
  return m ? m[1].trim() : null
}

describe('App Shell 契约', () => {
  it('tokens.css 定义了 --topnav-height（约 56px）', () => {
    const tokens = readCss('themes/tokens.css')
    const v = tokenValue(tokens, '--topnav-height')
    expect(v, 'tokens.css 缺少 --topnav-height').toBeTruthy()
    expect(v).toMatch(/56\s*px/)
  })

  it('tokens.css 定义了 --z-page-sticky，且数值低于 --z-nav', () => {
    const tokens = readCss('themes/tokens.css')
    const navZ = Number.parseFloat(tokenValue(tokens, '--z-nav') ?? 'NaN')
    const stickyZ = Number.parseFloat(tokenValue(tokens, '--z-page-sticky') ?? 'NaN')
    expect(Number.isFinite(navZ), '--z-nav 未定义').toBe(true)
    expect(Number.isFinite(stickyZ), '--z-page-sticky 未定义').toBe(true)
    expect(stickyZ).toBeLessThan(navZ)
  })

  it('.topnav 使用 var(--topnav-height) 作为高度，且 position:sticky top:0', () => {
    const appCss = readCss('app/app.css')
    const block = appCss.match(/\.topnav\s*\{([^}]+)\}/)
    expect(block, '.topnav 规则块未找到').toBeTruthy()
    const body = block![1]
    expect(body).toMatch(/position\s*:\s*sticky/)
    expect(body).toMatch(/top\s*:\s*0/)
    expect(body).toMatch(/height\s*:\s*var\(--topnav-height\)/)
    expect(body).toMatch(/z-index\s*:\s*var\(--z-nav\)/)
  })

  it('.wb4-bar 为非 sticky + flex-shrink:0（Workbench 4.0 顶栏，根级禁滚）', () => {
    const genCss = readCss('pages/Generate/generate.css')
    const block = genCss.match(/\.wb4-bar\s*\{([^}]+)\}/)
    expect(block, '.wb4-bar 规则块未找到').toBeTruthy()
    const body = block![1]
    expect(body).not.toMatch(/position\s*:\s*sticky/)
    expect(body).toMatch(/flex-shrink\s*:\s*0/)
  })

  it('响应式断点（v0.15）：存在 1199px 紧凑三栏与 1023px Workspace Tabs，且无 1319/1179 旧回退', () => {
    const genCss = readCss('pages/Generate/generate.css')
    expect(genCss).toMatch(/max-width\s*:\s*1199\s*px/)
    expect(genCss).toMatch(/max-width\s*:\s*1023\s*px/)
    // 历史 bug 回归：旧 1319 / 1179 回退必须彻底删除。
    expect(genCss).not.toMatch(/max-width\s*:\s*1319\s*px/)
    expect(genCss).not.toMatch(/max-width\s*:\s*1179\s*px/)
    const layoutCss = readCss('components/layout/layout.css')
    expect(layoutCss).not.toMatch(/max-width\s*:\s*1179\s*px/)
  })

  it('.app-shell 高度固定为 100dvh（不随内容纵向生长）', () => {
    const appCss = readCss('app/app.css')
    const block = appCss.match(/\.app-shell\s*\{([^}]+)\}/)
    expect(block, '.app-shell 规则块未找到').toBeTruthy()
    expect(block![1]).toMatch(/height\s*:\s*100dvh/)
  })

  it('.app-shell__main 默认滚动；--workspace 变体 overflow:hidden 禁止 Generate 撑长', () => {
    const appCss = readCss('app/app.css')
    const block = appCss.match(/\.app-shell__main\s*\{([^}]+)\}/)
    expect(block, '.app-shell__main 规则块未找到').toBeTruthy()
    expect(block![1]).toMatch(/overflow-y\s*:\s*auto/)
    expect(block![1]).toMatch(/min-height\s*:\s*0/)
    const ws = appCss.match(/\.app-shell__main--workspace\s*\{([^}]+)\}/)
    expect(ws, '.app-shell__main--workspace 规则块未找到').toBeTruthy()
    expect(ws![1]).toMatch(/overflow\s*:\s*hidden/)
  })
})
