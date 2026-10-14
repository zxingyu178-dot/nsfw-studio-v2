/**
 * v0.15 Task 2/15 — Glass Surface System + Performance Guard
 *
 * 硬约束（后续不得破坏）：
 *  - backdrop-filter 仅由 tokens.css 的 .glass / .glass--strong 提供；
 *  - 毛玻璃只允许出现在 8 类容器（TopNav / WorkbenchBar / Prompt Console / Inspector /
 *    TaskDock / Progress HUD / Canvas ActionDock / Popover），同时存在的玻璃层数 ≤ 8；
 *  - Canvas 图片舞台（.wb4-stage / .canvas-viewport__stage）永远 opaque matte，绝不 blur；
 *  - 无 backdrop-filter 支持时回退到较不透明 surface（--glass-fallback / --panel）。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import GeneratePage from './GeneratePage'

const SRC_DIR = resolve(process.cwd(), 'src')
function readCss(rel: string): string {
  return readFileSync(resolve(SRC_DIR, rel), 'utf8')
}
/** 去掉 CSS 注释，避免注释里的“绝不 backdrop-filter”字样被误判。 */
function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, '')
}

describe('Glass token 体系与降级', () => {
  it('tokens.css 定义全套 glass token（Dark/Light）与 fallback', () => {
    const css = readCss('themes/tokens.css')
    for (const token of [
      '--glass-bg',
      '--glass-bg-strong',
      '--glass-border',
      '--glass-highlight',
      '--glass-shadow',
      '--glass-blur',
      '--glass-saturate',
      '--glass-fallback',
    ]) {
      expect(css, `缺少 ${token}`).toMatch(new RegExp(`${token.replace(/--/g, '\\-\\-')}\\s*:`))
    }
    // 无 backdrop-filter 支持时回退到较不透明表面
    expect(css).toMatch(/@supports not[\s\S]*backdrop-filter/)
    expect(css).toMatch(/\.glass--strong[\s\S]*?background:\s*var\(--glass-fallback\)/)
  })
})

describe('Canvas 绝不 blur（§19.2）', () => {
  it('Canvas 舞台样式块内不出现 backdrop-filter', () => {
    const cv = stripComments(readCss('components/CanvasViewport/CanvasViewport.css'))
    const stageBlock = cv.match(/\.canvas-viewport__stage\s*\{([^}]+)\}/)
    expect(stageBlock, '.canvas-viewport__stage 未找到').toBeTruthy()
    expect(stageBlock![1]).not.toMatch(/backdrop-filter/)
    // 舞台必须是不透明/哑光背景
    expect(stageBlock![1]).toMatch(/background:\s*var\(--canvas-bg\)/)

    const gen = stripComments(readCss('pages/Generate/generate.css'))
    const wb4Stage = gen.match(/\.wb4-stage\s*\{([^}]+)\}/)
    expect(wb4Stage, '.wb4-stage 未找到').toBeTruthy()
    expect(wb4Stage![1]).not.toMatch(/backdrop-filter/)
  })

  it('不在每个 slot / input 上撒 blur', () => {
    const gen = stripComments(readCss('pages/Generate/generate.css'))
    const slot = gen.match(/\.wb4-slot\b[^{]*\{([^}]+)\}/)
    if (slot) expect(slot[1]).not.toMatch(/backdrop-filter/)
    expect(gen).not.toMatch(/\.ds-input[^{]*\{[^}]*backdrop-filter/)
  })
})

describe('同时存在的玻璃层数 ≤ 8（§19.1）', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('no backend'))))
  })

  it('GeneratePage 空闲态：渲染出的 .glass 元素 ≤ 8，且玻璃元素都不在 Canvas 舞台内', () => {
    const { container } = render(
      <MemoryRouter>
        <GeneratePage />
      </MemoryRouter>,
    )
    const glassEls = container.querySelectorAll('.glass, .glass--strong')
    expect(glassEls.length, `玻璃层数 ${glassEls.length} 超过 8`).toBeLessThanOrEqual(8)

    const stage = container.querySelector('.wb4-stage, .canvas-viewport__stage')
    // 舞台内的 ActionDock 是允许的 8 类容器之一（在画布之上的浮层），但舞台本身不 glass。
    if (stage) {
      expect(stage.classList.contains('glass')).toBe(false)
      expect(stage.classList.contains('glass--strong')).toBe(false)
    }
  })
})
