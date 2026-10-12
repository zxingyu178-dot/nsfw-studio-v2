/**
 * Phase 0.12 App Shell / Sticky / Responsive 契约测试
 *
 * 硬约束（后续 agent 不得破坏）：
 * 1. --topnav-height 在 tokens.css 中定义（56px）。
 * 2. TopNav 与页面内 sticky（Generate modebar）使用同一高度 token，避免 modebar 盖导航。
 * 3. z-index 契约：--z-nav > --z-page-sticky（页内 sticky 永远在一级导航之下）。
 * 4. Generate modebar 必须 top: var(--topnav-height)（不再 top:0）。
 * 5. 响应式断点：≥1320 三栏；1180~1319 压缩三栏；<1180 单栏堆叠。
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

  it('.generate__modebar 必须 top: var(--topnav-height)（不再 top:0），且 z-index 用 --z-page-sticky', () => {
    const genCss = readCss('pages/Generate/generate.css')
    const block = genCss.match(/\.generate__modebar\s*\{([^}]+)\}/)
    expect(block, '.generate__modebar 规则块未找到').toBeTruthy()
    const body = block![1]
    expect(body).toMatch(/position\s*:\s*sticky/)
    expect(body).toMatch(/top\s*:\s*var\(--topnav-height\)/)
    expect(body).not.toMatch(/top\s*:\s*0\s*;/)
    expect(body).toMatch(/z-index\s*:\s*var\(--z-page-sticky\)/)
  })

  it('响应式断点：存在 1319px 与 1179px 两档 media query', () => {
    const genCss = readCss('pages/Generate/generate.css')
    expect(genCss).toMatch(/max-width\s*:\s*1319\s*px/)
    expect(genCss).toMatch(/max-width\s*:\s*1179\s*px/)
    expect(genCss).not.toMatch(/max-width\s*:\s*1100\s*px/)
  })

  it('.app-shell 高度固定为 100dvh（不随内容纵向生长）', () => {
    const appCss = readCss('app/app.css')
    const block = appCss.match(/\.app-shell\s*\{([^}]+)\}/)
    expect(block, '.app-shell 规则块未找到').toBeTruthy()
    expect(block![1]).toMatch(/height\s*:\s*100dvh/)
  })

  it('.app-shell__main 作为滚动容器（overflow-y:auto），min-height:0', () => {
    const appCss = readCss('app/app.css')
    const block = appCss.match(/\.app-shell__main\s*\{([^}]+)\}/)
    expect(block, '.app-shell__main 规则块未找到').toBeTruthy()
    expect(block![1]).toMatch(/overflow-y\s*:\s*auto/)
    expect(block![1]).toMatch(/min-height\s*:\s*0/)
  })
})
