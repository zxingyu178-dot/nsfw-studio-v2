/**
 * generate.css 静态去重 guard（§6）：
 * - 剔除注释与 @media 内嵌规则后，统计核心组件选择器的“顶层主声明”次数；
 * - 同一组件主样式（含 :hover/:active/:disabled）出现 ≥2 次即 fail——
 *   禁止后文用重复 selector 修正前文；responsive override 只允许出现在 @media 内。
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const CSS_PATH = path.join(path.dirname(fileURLToPath(import.meta.url)), 'generate.css')

/** 收集顶层规则头（深度 0 时的选择器文本）；@media 内的规则因深度 >0 被跳过。 */
function topLevelRuleHeaders(css: string): string[] {
  const cleaned = css.replace(/\/\*[\s\S]*?\*\//g, '')
  const headers: string[] = []
  let depth = 0
  let buf = ''
  for (const ch of cleaned) {
    if (ch === '{') {
      if (depth === 0) headers.push(buf.trim())
      buf = ''
      depth++
    } else if (ch === '}') {
      depth--
    } else if (depth === 0) {
      buf += ch
    }
  }
  return headers.filter(Boolean)
}

describe('generate.css 核心组件主样式唯一（去重 guard）', () => {
  const headers = topLevelRuleHeaders(fs.readFileSync(CSS_PATH, 'utf8'))

  it.each([
    '.generate-action',
    '.generate-action:hover:not(:disabled)',
    '.generate-action:active:not(:disabled)',
    '.generate-action:disabled',
    // task dock（任务卡片动作行）
    '.wb-job__actions',
    // canvas action dock（悬浮图片动作坞）
    '.wb-canvas__dock',
  ])('顶层主声明 %s 恰好出现 1 次', (selector) => {
    const count = headers.filter((h) => h === selector).length
    expect(count, `选择器 ${selector} 出现 ${count} 次；禁止重复主声明`).toBe(1)
  })

  it('不存在裸 .generate-action 被后文重复定义（BEM 子元素不算重复主声明）', () => {
    const bare = headers.filter(
      (h) => h === '.generate-action' || (h.startsWith('.generate-action:') && !h.startsWith('.generate-action__')),
    )
    // 应只剩：.generate-action / :hover / :active / :disabled 共 4 条
    expect(bare).toEqual([
      '.generate-action',
      '.generate-action:hover:not(:disabled)',
      '.generate-action:active:not(:disabled)',
      '.generate-action:disabled',
    ])
  })
})
