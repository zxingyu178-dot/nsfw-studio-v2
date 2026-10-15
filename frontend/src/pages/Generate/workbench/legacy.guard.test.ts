/**
 * v0.15.1 no-production-import guard：
 * 0.14 的 ResultPane / GenerationControls 已被 Workbench 4.0（CanvasStage / InspectorPanel）
 * 取代并删除。生产代码不得再引用这两个旧模块，避免“同一业务两套实现 / 测试在验证 legacy”。
 * 本测试遍历 src 下所有非测试源文件，一旦发现旧模块被重新引入或文件被还原即失败。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const srcRoot = resolve(here, '..', '..', '..', '..') // frontend/src

const LEGACY_FILES = [
  join(srcRoot, 'pages', 'Generate', 'ResultPane.tsx'),
  join(srcRoot, 'pages', 'Generate', 'components', 'GenerationControls.tsx'),
]
const FORBIDDEN_SPECIFIERS = ['ResultPane', 'GenerationControls']

function collectSourceFiles(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry.startsWith('.')) continue
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      out.push(...collectSourceFiles(full))
    } else if (/\.(ts|tsx)$/.test(entry) && !/\.(test|spec)\.(ts|tsx)$/.test(entry)) {
      out.push(full)
    }
  }
  return out
}

describe('legacy Generate 组件清理守卫', () => {
  it('旧 ResultPane.tsx / GenerationControls.tsx 已从生产树删除', () => {
    for (const file of LEGACY_FILES) {
      expect(existsSync(file), `legacy 文件不应存在: ${file}`).toBe(false)
    }
  })

  it('生产代码中不存在任何对 legacy 模块的 import / re-export', () => {
    const offenders: string[] = []
    for (const file of collectSourceFiles(srcRoot)) {
      const content = readFileSync(file, 'utf8')
      const importLines = content
        .split('\n')
        .filter((line) => /^\s*(import|export)\b/.test(line))
      for (const line of importLines) {
        if (FORBIDDEN_SPECIFIERS.some((name) => line.includes(name)) && line.includes('from')) {
          offenders.push(`${file}: ${line.trim()}`)
        }
      }
    }
    expect(offenders).toEqual([])
  })
})
