/**
 * Phase 0.12 Design Token Closure Guard
 *
 * 扫描 frontend/src 下所有 CSS 文件：
 * 1. 从 tokens.css 收集全局设计 token 定义（:root / [data-theme='light']）。
 * 2. 收集所有 CSS 中的 var(--xxx[, fallback]) 引用。
 * 3. 对每个"无 fallback 的引用"，若该 token 既不在全局定义中、
 *    也不在组件局部变量白名单中、也未在同一文件内定义，则 fail。
 *
 * 这是后续所有 agent 的硬约束：新增全局 token 必须在 tokens.css 中定义，
 * 否则本测试会红。组件局部变量（如 --ds-slider-pct）通过白名单放行。
 *
 * 实现说明：vitest 下 css:false 会让 import.meta.glob('?raw') 拿到空字符串，
 * 因此这里直接用 node:fs 读源码文件，保证测试稳定。
 */
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

// vitest 从 frontend/ 目录启动，src/ 即 process.cwd()/src。
const SRC_DIR = resolve(process.cwd(), 'src')

function walkCss(dir: string, acc: Array<{ path: string; content: string }> = []): typeof acc {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === 'dist' || entry.name.startsWith('.')) continue
      walkCss(full, acc)
    } else if (entry.name.endsWith('.css')) {
      acc.push({ path: full, content: readFileSync(full, 'utf8') })
    }
  }
  return acc
}

const ALL_CSS = walkCss(SRC_DIR)
const TOKENS_CSS = ALL_CSS.find((f) => f.path.replace(/\\/g, '/').endsWith('themes/tokens.css'))!

// 组件局部变量白名单：这些变量在组件 CSS 内自包含定义，不要求在 tokens.css 中声明。
const LOCAL_WHITELIST = new Set<string>([
  '--ds-slider-pct', // ui.css 滑块百分比，组件内部状态
])

function extractTokenDefs(css: string): Set<string> {
  const set = new Set<string>()
  const re = /(--[a-zA-Z][a-zA-Z0-9-]*)\s*:/g
  let m: RegExpExecArray | null
  while ((m = re.exec(css)) !== null) set.add(m[1])
  return set
}

interface VarRef {
  name: string
  hasFallback: boolean
}
function extractVarRefs(css: string): VarRef[] {
  const refs: VarRef[] = []
  const re = /var\(\s*(--[a-zA-Z][a-zA-Z0-9-]*)\s*/g
  let m: RegExpExecArray | null
  while ((m = re.exec(css)) !== null) {
    const name = m[1]
    let i = m.index + m[0].length
    let depth = 1
    let hasFallback = false
    while (i < css.length && depth > 0) {
      const ch = css[i]
      if (ch === '(') depth++
      else if (ch === ')') depth--
      else if (ch === ',' && depth === 1) {
        hasFallback = true
        break
      }
      i++
    }
    refs.push({ name, hasFallback })
  }
  return refs
}

describe('design_tokens 守卫：所有 var() 引用必须有全局定义或 fallback', () => {
  it('能扫描到 tokens.css 与所有组件 CSS', () => {
    expect(TOKENS_CSS, '未找到 tokens.css').toBeTruthy()
    expect(ALL_CSS.length).toBeGreaterThan(10)
  })

  it('tokens.css 中定义了 Phase 0.12 要求的全部 alias', () => {
    const globals = extractTokenDefs(TOKENS_CSS.content)
    const required = [
      '--text',
      '--text-primary',
      '--text-secondary',
      '--text-tertiary',
      '--success',
      '--success-soft',
      '--danger-soft',
      '--on-accent',
      '--radius-xs',
      '--weight-medium',
      '--weight-semibold',
      '--weight-bold',
      '--font-mono',
      '--mono',
      '--leading-relaxed',
      '--favorite',
      '--favorite-bg',
      '--topnav-height',
      '--z-page-sticky',
    ]
    const missing = required.filter((t) => !globals.has(t))
    expect(missing, `tokens.css 缺少以下全局 token: ${missing.join(', ')}`).toEqual([])
  })

  it('无 fallback 的 var() 引用必须落在全局定义、白名单或同文件局部定义中', () => {
    const globals = extractTokenDefs(TOKENS_CSS.content)
    const undefinedRefs: Array<{ file: string; name: string }> = []
    for (const { path, content } of ALL_CSS) {
      const localDefs = extractTokenDefs(content)
      for (const ref of extractVarRefs(content)) {
        if (ref.hasFallback) continue
        if (globals.has(ref.name)) continue
        if (LOCAL_WHITELIST.has(ref.name)) continue
        if (localDefs.has(ref.name)) continue
        undefinedRefs.push({ file: path, name: ref.name })
      }
    }
    if (undefinedRefs.length > 0) {
      const grouped = new Map<string, string[]>()
      for (const r of undefinedRefs) {
        if (!grouped.has(r.name)) grouped.set(r.name, [])
        grouped.get(r.name)!.join(r.file)
        grouped.get(r.name)!.push(r.file)
      }
      const lines = Array.from(grouped.entries()).map(
        ([name, files]) => `  ${name}  ←  ${files.join(', ')}`,
      )
      throw new Error(
        `以下 var() 引用未定义为全局 token（也无 fallback / 不在白名单）：\n${lines.join('\n')}\n` +
          `请在 frontend/src/themes/tokens.css 中追加定义，或为引用处加 fallback。`,
      )
    }
    expect(undefinedRefs).toEqual([])
  })

  it('禁止硬编码收藏色 #f5a623（必须改用 var(--favorite)）', () => {
    // tokens.css 中 --favorite: #f5a623 是规范定义，不算硬编码；其他 CSS 不得直接出现。
    const offenders: string[] = []
    for (const { path, content } of ALL_CSS) {
      if (path.replace(/\\/g, '/').endsWith('themes/tokens.css')) continue
      if (/#f5a623/i.test(content)) offenders.push(path)
    }
    expect(offenders, `以下 CSS 仍硬编码 #f5a623，请改用 var(--favorite)：${offenders.join(', ')}`).toEqual([])
  })
})
