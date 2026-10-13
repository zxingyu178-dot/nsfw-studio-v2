/**
 * Tooltip 轻量测试：悬停 / 聚焦显示，role=tooltip + aria-describedby 关联。
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Tooltip } from './Tooltip'

describe('Tooltip', () => {
  it('默认不渲染浮层，悬停后出现 role=tooltip', async () => {
    const user = userEvent.setup()
    render(
      <Tooltip content="上一张">
        <button type="button">btn</button>
      </Tooltip>,
    )
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    await user.hover(screen.getByRole('button'))
    const tip = screen.getByRole('tooltip')
    expect(tip).toHaveTextContent('上一张')
    const trigger = screen.getByRole('button').closest('.ui3-tooltip-trigger') as HTMLElement
    expect(trigger).toHaveAttribute('aria-describedby', tip.id)
  })

  it('content 为空时透传 children、不包裹', () => {
    render(
      <Tooltip content="">
        <button type="button">plain</button>
      </Tooltip>,
    )
    expect(screen.getByRole('button')).toBeInTheDocument()
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })
})
