import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import { CHOICE_TILE_LONG_EDGE, ChoiceTile, shapePixels } from './ChoiceTile'

describe('ChoiceTile 画幅预览', () => {
  it('1:1 是正方形', () => {
    expect(shapePixels('1:1')).toEqual({
      width: CHOICE_TILE_LONG_EDGE,
      height: CHOICE_TILE_LONG_EDGE,
    })
  })

  it('16:9 是横框，9:16 是竖框，3:4 是竖框', () => {
    const landscape = shapePixels('16:9')
    const portrait = shapePixels('9:16')
    const portrait34 = shapePixels('3:4')

    expect(landscape.width).toBeGreaterThan(landscape.height)
    expect(portrait.height).toBeGreaterThan(portrait.width)
    expect(portrait34.height).toBeGreaterThan(portrait34.width)
  })

  it('不同画幅渲染出不同的像素尺寸（回归：此前所有瓦片都是 28x28）', () => {
    render(
      <div>
        <ChoiceTile shape="1:1" label="1:1" />
        <ChoiceTile shape="16:9" label="16:9" />
        <ChoiceTile shape="9:16" label="9:16" />
      </div>,
    )

    const square = screen.getByRole('button', { name: '1:1' })
    const landscape = screen.getByRole('button', { name: '16:9' })
    const portrait = screen.getByRole('button', { name: '9:16' })

    const inner = (el: HTMLElement) => el.querySelector('.ui3-tile__shape-inner') as HTMLElement

    expect(inner(square).style.width).toBe('28px')
    expect(inner(square).style.height).toBe('28px')

    expect(inner(landscape).style.width).toBe('28px')
    expect(inner(landscape).style.height).not.toBe('28px')

    expect(inner(portrait).style.height).toBe('28px')
    expect(inner(portrait).style.width).not.toBe('28px')

    // 关键回归断言：横框与竖框不能长得一样
    expect(inner(landscape).style.width).not.toBe(inner(portrait).style.width)
    expect(inner(landscape).style.height).not.toBe(inner(portrait).style.height)
  })

  it('selected 时带 aria-pressed，禁用时 disabled', () => {
    render(
      <div>
        <ChoiceTile shape="1:1" label="选中" selected />
        <ChoiceTile shape="1:1" label="禁用" disabled />
      </div>,
    )

    expect(screen.getByRole('button', { name: '选中' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '禁用' })).toBeDisabled()
  })
})
