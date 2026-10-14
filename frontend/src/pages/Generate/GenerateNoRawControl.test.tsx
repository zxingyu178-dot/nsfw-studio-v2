import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import GeneratePage from './GeneratePage'

const GEN_DIR = path.dirname(fileURLToPath(import.meta.url))
const SRC_DIR = path.resolve(GEN_DIR, '../..')

/**
 * 业务层控件语义规则（§7，替代旧“一刀切禁止原生 button”）：
 *
 * 【豁免目录（显式列清）】
 *  - src/components/ui/**（UI primitive 层，Tabs.tsx 的原生 button 是标准 WAI-ARIA 实现，正确且允许）；
 *  - src/components/ui/ui3/**（ChoiceTile / NumberStepper / IconButton / DisclosureButton 等 primitive 内部原生控件）；
 *  - src/pages/Generate/components/GenerateAction.tsx（业务层唯一被允许的原生 <button>，专属主按钮豁免）；
 *  - src/pages/Generate/proto/**（WIP 原型目录，本规则不扫描）；
 *  - *.test.tsx / *.test.ts（测试文件本身）。
 *
 * 【规则】
 *  1. 业务页禁止“裸”原生 <button>/<select>：开标签内没有 className（无 DS 类、无样式收口）即违规；
 *     允许并要求 DS 大写组件（IconButton/ActionButton/DisclosureButton/Tabs 等）。
 *  2. 业务页禁止 hand-rolled div[role="button"] / div[role="tab"]（伪控件），
 *     应改用 ui3 DisclosureButton / DS Tabs。
 *  3. Generate 主链不新增原生 <select>（PopoverSelect 收口，§8）。
 */
const EXEMPT_REL_PREFIXES = [
  'components/ui/',
  'components/ui/ui3/',
]
const EXEMPT_EXACT = ['components/GenerateAction.tsx']
const EXEMPT_DIR_NAMES = ['proto']

function listSourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (EXEMPT_DIR_NAMES.includes(entry.name)) continue
      listSourceFiles(full, out)
    } else if (entry.name.endsWith('.tsx') && !entry.name.endsWith('.test.tsx') && !entry.name.endsWith('.test.ts')) {
      out.push(full)
    }
  }
  return out
}

function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

function isExempt(relUnix: string): boolean {
  if (EXEMPT_EXACT.some((ex) => relUnix === ex)) return true
  return EXEMPT_REL_PREFIXES.some((p) => relUnix.startsWith(p))
}

/** 检查“裸”原生标签（开标签内无 className）。 */
function checkNakedControl(src: string, tag: 'button' | 'select'): boolean {
  const re = new RegExp(`<${tag}\\b([\\s\\S]*?)>`, 'g')
  let m: RegExpExecArray | null
  while ((m = re.exec(src))) {
    const attrs = m[1] ?? ''
    if (!/className=/.test(attrs)) return true
  }
  return false
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('no backend'))))
})

describe('GenerateNoRawControl（业务层控件语义规则）', () => {
  it('渲染整页后 DOM 中不出现原生 <select>', () => {
    render(
      <MemoryRouter>
        <GeneratePage />
      </MemoryRouter>,
    )
    expect(document.querySelector('select')).toBeNull()
  })

  it('Generate 业务 .tsx 不得出现裸原生 <button>/<select>（GenerateAction 专属豁免除外）', () => {
    const offenders: string[] = []
    for (const file of listSourceFiles(GEN_DIR)) {
      const rel = path.relative(GEN_DIR, file).replace(/\\/g, '/')
      if (isExempt(rel)) continue
      const cleaned = stripComments(fs.readFileSync(file, 'utf8'))
      if (checkNakedControl(cleaned, 'select')) offenders.push(`${rel}: 裸 <select>`)
      if (checkNakedControl(cleaned, 'button')) offenders.push(`${rel}: 裸 <button>`)
    }
    expect(offenders).toEqual([])
  })

  it('全业务页禁止 hand-rolled div[role="button"]/div[role="tab"]（应收口到 ui3/DS Tabs）', () => {
    const pagesDir = path.resolve(SRC_DIR, 'pages')
    const offenders: string[] = []
    for (const file of listSourceFiles(pagesDir)) {
      const rel = path.relative(SRC_DIR, file).replace(/\\/g, '/')
      const cleaned = stripComments(fs.readFileSync(file, 'utf8'))
      if (/<div[^>]*\brole="button"/.test(cleaned)) offenders.push(`${rel}: div[role="button"]`)
      if (/<div[^>]*\brole="tab"/.test(cleaned)) offenders.push(`${rel}: div[role="tab"]`)
    }
    expect(offenders).toEqual([])
  })
})
