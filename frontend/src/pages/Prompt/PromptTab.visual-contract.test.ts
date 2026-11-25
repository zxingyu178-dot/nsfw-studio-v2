import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const promptCss = readFileSync(resolve(process.cwd(), 'src/pages/Prompt/prompt.css'), 'utf8')

describe('Prompt 紧凑卡片视觉契约', () => {
  it('让日用图片工具、行内改名和状态下拉适配媒体列布局', () => {
    expect(promptCss).toMatch(
      /\.pp-grid--single \.pp-card--compact \.pp-card__gallery-tools\s*\{[^}]*padding:\s*0/s,
    )
    expect(promptCss).toMatch(
      /\.pp-grid--single \.pp-card--compact \.pp-card__title-input\s*\{[^}]*max-width:\s*100%/s,
    )
    expect(promptCss).toMatch(
      /\.pp-grid--single \.pp-card--compact \.pp-card__status-select\s*\{[^}]*max-width:\s*100%/s,
    )
  })
})
