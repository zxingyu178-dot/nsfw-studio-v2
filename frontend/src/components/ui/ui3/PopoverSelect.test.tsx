/**
 * PopoverSelect 测试：渲染 / ARIA 角色、↑↓ 高亮、Enter 选中、
 * Esc 关闭、typeahead 前缀匹配、点击外部关闭。
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PopoverSelect } from './PopoverSelect'

const options = [
  { value: 'sd15', label: 'SD 1.5' },
  { value: 'sdxl', label: 'SDXL' },
  { value: 'flux', label: 'Flux' },
]

describe('PopoverSelect', () => {
  it('渲染当前选中值', () => {
    render(<PopoverSelect value="sdxl" onChange={() => {}} options={options} />)
    expect(screen.getByRole('button')).toHaveTextContent('SDXL')
  })

  it('点击触发器打开 listbox（ARIA 角色齐全）', async () => {
    const user = userEvent.setup()
    render(<PopoverSelect value="sd15" onChange={() => {}} options={options} />)
    const trigger = screen.getByRole('button')
    expect(trigger).toHaveAttribute('aria-haspopup', 'listbox')
    await user.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    const listbox = screen.getByRole('listbox')
    expect(listbox).toBeInTheDocument()
    expect(screen.getAllByRole('option')).toHaveLength(3)
  })

  it('↑↓ 移动高亮、Enter 选中对应项', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<PopoverSelect value="sd15" onChange={onChange} options={options} />)
    await user.click(screen.getByRole('button'))
    await user.keyboard('{ArrowDown}') // -> sdxl
    await user.keyboard('{ArrowDown}') // -> flux
    await user.keyboard('{Enter}')
    expect(onChange).toHaveBeenCalledWith('flux')
  })

  it('Esc 关闭浮层', async () => {
    const user = userEvent.setup()
    render(<PopoverSelect value="sd15" onChange={() => {}} options={options} />)
    await user.click(screen.getByRole('button'))
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('typeahead 输入字符前缀匹配', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<PopoverSelect value="sd15" onChange={onChange} options={options} />)
    await user.click(screen.getByRole('button'))
    await user.keyboard('f') // 高亮 Flux
    await user.keyboard('{Enter}')
    expect(onChange).toHaveBeenCalledWith('flux')
  })

  it('点击外部关闭浮层', async () => {
    const user = userEvent.setup()
    render(
      <>
        <div data-testid="outside" />
        <PopoverSelect value="sd15" onChange={() => {}} options={options} />
      </>,
    )
    await user.click(screen.getByRole('button'))
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    await user.click(screen.getByTestId('outside'))
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
})
