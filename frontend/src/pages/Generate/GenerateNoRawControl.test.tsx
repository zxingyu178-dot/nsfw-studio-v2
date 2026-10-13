import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import GeneratePage from './GeneratePage'

const GEN_DIR = path.dirname(fileURLToPath(import.meta.url))

function listSourceFiles(dir: string): string[] {
  const out: string[] = []
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) out.push(...listSourceFiles(full))
    else if (entry.name.endsWith('.tsx') && !entry.name.endsWith('.test.tsx')) out.push(full)
  }
  return out
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('no backend'))))
})

function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

describe('GenerateNoRawControl（业务层禁止原生控件）', () => {
  it('渲染整页后 DOM 中不出现原生 <select>', () => {
    render(
      <MemoryRouter>
        <GeneratePage />
      </MemoryRouter>,
    )
    expect(document.querySelector('select')).toBeNull()
  })

  it('业务 .tsx 源码不得出现原生 <select>/<button>（仅专属 GenerateAction 允许 <button>）', () => {
    const offenders: string[] = []
    for (const file of listSourceFiles(GEN_DIR)) {
      const rel = path.relative(GEN_DIR, file).replace(/\\/g, '/')
      const cleaned = stripComments(fs.readFileSync(file, 'utf8'))
      // 仅匹配小写原生标签；DS <Button> 组件、注释文本不计入。
      if (/<select[\s/>]/.test(cleaned)) offenders.push(`${rel}: native <select>`)
      if (/<button[\s/>]/.test(cleaned) && rel !== 'components/GenerateAction.tsx') {
        offenders.push(`${rel}: native <button>`)
      }
    }
    expect(offenders).toEqual([])
  })
})
