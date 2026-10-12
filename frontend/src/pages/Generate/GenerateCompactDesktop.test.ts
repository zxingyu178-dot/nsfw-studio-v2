/**
 * Phase 0.13：1024~1319 紧凑三栏不堆叠契约
 *
 * 目标：1024×600 仍三栏一屏（中间预览优先保宽，左右先压），gap/padding/header 紧凑。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const SRC_DIR = resolve(process.cwd(), 'src')
function readCss(relPath: string): string {
  return readFileSync(resolve(SRC_DIR, relPath), 'utf8')
}

describe('GenerateCompactDesktop：1024~1319 紧凑三栏不堆叠', () => {
  it('存在 max-width:1319px 媒体查询，把 columns 压成 minmax 三栏（不堆叠为 1fr）', () => {
    const css = readCss('pages/Generate/generate.css')
    const mq = css.match(/@media\s*\(max-width:\s*1319px\)\s*\{([\s\S]*?)\n\}/)
    expect(mq, '1319px 媒体查询未找到').toBeTruthy()
    const block = mq![1]
    // 三栏 minmax（中间列最宽），不得是单列 1fr
    expect(block).toMatch(/grid-template-columns\s*:\s*minmax/)
    expect(block).toMatch(/minmax\(320px/)
    expect(block).not.toMatch(/grid-template-columns\s*:\s*1fr/)
  })

  it('紧凑档压缩 gap 与 padding（≤space-3 量级），并紧凑 pane header/body/footer', () => {
    const css = readCss('pages/Generate/generate.css')
    const mq = css.match(/@media\s*\(max-width:\s*1319px\)\s*\{([\s\S]*?)\n\}/)
    const block = mq![1]
    expect(block).toMatch(/gap\s*:\s*var\(--space-2\)/)
    expect(block).toMatch(/\.wb-pane__header/)
    expect(block).toMatch(/\.wb-pane__body/)
    expect(block).toMatch(/\.wb-pane__footer/)
  })

  it('紧凑档隐藏 modebar 右侧长解释（只留 文生图 | 图片生成）', () => {
    const css = readCss('pages/Generate/generate.css')
    const mq = css.match(/@media\s*\(max-width:\s*1319px\)\s*\{([\s\S]*?)\n\}/)
    expect(mq![1]).toMatch(/\.generate__modebar-hint\s*\{\s*display\s*:\s*none/)
  })
})
