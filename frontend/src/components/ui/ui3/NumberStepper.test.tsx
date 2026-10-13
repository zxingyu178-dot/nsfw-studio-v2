/**
 * NumberStepper 测试：+/- 步进、min/max 钳制、直接输入非法值钳制、快捷 chips。
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { NumberStepper } from './NumberStepper'

describe('NumberStepper', () => {
  it('+ / - 按 step 步进', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<NumberStepper value={4} onChange={onChange} min={1} max={8} />)
    await user.click(screen.getByLabelText('加'))
    expect(onChange).toHaveBeenLastCalledWith(5)
    await user.click(screen.getByLabelText('减'))
    expect(onChange).toHaveBeenLastCalledWith(3)
  })

  it('达到 min 禁用减号、达到 max 禁用加号', () => {
    render(<NumberStepper value={1} onChange={() => {}} min={1} max={8} />)
    expect(screen.getByLabelText('减')).toBeDisabled()
  })

  it('达到 max 时禁用加号', () => {
    render(<NumberStepper value={8} onChange={() => {}} min={1} max={8} />)
    expect(screen.getByLabelText('加')).toBeDisabled()
  })

  it('直接输入越界值后失焦钳制到 max', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<NumberStepper value={4} onChange={onChange} min={1} max={8} />)
    const input = screen.getByLabelText('数值') as HTMLInputElement
    await user.clear(input)
    await user.type(input, '99')
    await user.tab() // 触发 blur -> commit
    expect(onChange).toHaveBeenCalledWith(8)
  })

  it('快捷 chips 可直接选择', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<NumberStepper value={1} onChange={onChange} min={1} max={8} chips={[1, 2, 4, 6, 8]} />)
    await user.click(screen.getByText('4'))
    expect(onChange).toHaveBeenCalledWith(4)
  })
})
