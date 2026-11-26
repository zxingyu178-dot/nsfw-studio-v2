import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { NsfwPromptDrawer } from './NsfwPromptDrawer'
import {
  NSFW_LEVELS,
  NSFW_TAG_GROUPS,
  appendPromptTag,
  buildLevelNegative,
  buildLevelPrompt,
  type NsfwLevel,
} from './nsfwPresets'

function setup(mode: 'structured' | 'full' = 'full', initialLevel?: NsfwLevel) {
  const onApplyTemplate = vi.fn()
  const onAppendTag = vi.fn()
  render(
    <NsfwPromptDrawer
      mode={mode}
      targetLabel="完整 Prompt"
      initialLevel={initialLevel}
      onClose={vi.fn()}
      onApplyTemplate={onApplyTemplate}
      onAppendTag={onAppendTag}
    />,
  )
  return { onApplyTemplate, onAppendTag }
}

describe('NSFW 分级词库（集成自 nsfw-v2-pipeline skill，v0.37.7 扩充）', () => {
  it('默认套用 MiaoMiao 体系 L1 第一套模板，负向固定带未成年压制词', () => {
    const { onApplyTemplate } = setup()

    fireEvent.click(screen.getAllByRole('button', { name: '套用' })[0])

    expect(onApplyTemplate).toHaveBeenCalledTimes(1)
    const [positive, negative] = onApplyTemplate.mock.calls[0]
    expect(positive).toContain('score_9')
    expect(positive).toContain('rating_sensitive')
    expect(positive).toContain('onsen')
    expect(negative).toContain('child')
    expect(negative).toContain('loli')
  })

  it('切到 WAI 体系与 L3 页签后使用对应质量词、评级词与场景模板', () => {
    const { onApplyTemplate } = setup()

    fireEvent.click(screen.getByRole('button', { name: /WAI v15/ }))
    fireEvent.click(screen.getByRole('tab', { name: /L3 explicit/ }))
    fireEvent.click(screen.getAllByRole('button', { name: '套用' })[0])

    const [positive] = onApplyTemplate.mock.calls[0]
    expect(positive).toContain('masterpiece')
    expect(positive).toContain('nsfw, explicit')
    expect(positive).toBe(buildLevelPrompt('L3', 'wai'))
  })

  it('分级页签展示每档模板数量，切换后展示该档模板', () => {
    setup(undefined, 'L3')

    // initialLevel 直接定位到 L3
    expect(screen.getByText('传教士 · 床')).toBeInTheDocument()
    expect(screen.getByText('后入 · 沙发')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '套用' })).toHaveLength(
      NSFW_LEVELS.find((item) => item.level === 'L3')!.variants.length,
    )

    fireEvent.click(screen.getByRole('tab', { name: /L2 擦边级/ }))
    expect(screen.getByText('黑蕾丝床躺')).toBeInTheDocument()
    expect(screen.queryByText('传教士 · 床')).toBeNull()
  })

  it('标签库按分类页签切换，默认位次分类可直接追加', () => {
    const { onAppendTag } = setup('structured')

    expect(screen.getByText(/点击追加到：完整 Prompt/)).toBeTruthy()
    fireEvent.click(screen.getByTitle('传教士位 — missionary'))
    expect(onAppendTag).toHaveBeenCalledWith('missionary')

    // 切到场景分类后显示场景标签，位次标签收起
    fireEvent.click(screen.getByRole('tab', { name: /场景 \/ 环境/ }))
    expect(screen.getByTitle('卧室 — bedroom')).toBeInTheDocument()
    expect(screen.queryByTitle('传教士位 — missionary')).toBeNull()
  })

  it('结构化模式下提示会切换到完整模式', () => {
    setup('structured')
    expect(screen.getByText(/当前是结构化模式/)).toBeTruthy()
  })

  it('模板与负向基线包含成年锚定与安全词', () => {
    const positive = buildLevelPrompt('L2', 'miao')
    const negative = buildLevelNegative('miao')
    expect(positive).toContain('mature female')
    expect(positive).toContain('25 years old')
    expect(negative).toContain('child')
    expect(negative).toContain('worst quality')
  })

  it('词库规模已扩充：模板 13 套、标签分组 15 类、标签 300+', () => {
    const templateCount = NSFW_LEVELS.reduce((total, item) => total + item.variants.length, 0)
    const tagCount = NSFW_TAG_GROUPS.reduce((total, group) => total + group.tags.length, 0)
    expect(templateCount).toBe(13)
    expect(NSFW_TAG_GROUPS).toHaveLength(15)
    expect(tagCount).toBeGreaterThanOrEqual(300)
  })

  it('简称套装展开为完整提示词，并按详细度加深背景', () => {
    const { onAppendTag } = setup()

    fireEvent.click(screen.getByRole('tab', { name: /制服 \/ 角色扮演/ }))
    const jk = screen.getByTitle(/华丽绿色 JK — green school uniform/)
    expect(jk.className).toContain('nsfw-lib__chip--d3')
    expect(jk).toHaveTextContent('+12 标签')
    fireEvent.click(jk)
    const payload = onAppendTag.mock.calls[0][0]
    expect(payload).toContain('green blazer')
    expect(payload).toContain('green pleated skirt')
    expect(payload.split(',').length).toBeGreaterThanOrEqual(10)
  })

  it('画师按模型体系切换写法，并带悬停简介', () => {
    const { onAppendTag } = setup()

    fireEvent.click(screen.getByRole('tab', { name: /画师风格/ }))
    const wlop = screen.getByTitle(/wlop — @wlop/)
    expect(wlop).toHaveAttribute('data-tip')
    expect(wlop.getAttribute('data-tip')).toContain('厚涂')
    fireEvent.click(wlop)
    expect(onAppendTag).toHaveBeenLastCalledWith('@wlop')

    fireEvent.click(screen.getByRole('button', { name: /WAI v15/ }))
    fireEvent.click(screen.getByTitle(/wlop — wlop/))
    expect(onAppendTag).toHaveBeenLastCalledWith('wlop')
  })

  it('画面风格分类可用，且条目带简介', () => {
    const { onAppendTag } = setup()

    fireEvent.click(screen.getByRole('tab', { name: /画面风格/ }))
    const chip = screen.getByTitle('柔和赛璐璐 — soft cel shading')
    expect(chip.getAttribute('data-tip')).toContain('明暗')
    fireEvent.click(chip)
    expect(onAppendTag).toHaveBeenCalledWith('soft cel shading')
  })

  it('appendPromptTag 追加去重且保持逗号分隔', () => {
    expect(appendPromptTag('', 'adult')).toBe('adult')
    expect(appendPromptTag('adult, solo', 'missionary')).toBe('adult, solo, missionary')
    expect(appendPromptTag('adult, solo', 'adult')).toBe('adult, solo')
    expect(appendPromptTag('adult,  solo ', 'nipples')).toBe('adult, solo, nipples')
  })
})
