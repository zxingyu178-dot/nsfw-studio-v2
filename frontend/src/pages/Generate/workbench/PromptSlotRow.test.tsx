import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { PromptSlotRow } from './PromptSlotRow'

describe('PromptSlotRow 占位文案', () => {
  it('标签以「描述」结尾时不重复拼「描述」', () => {
    render(
      <PromptSlotRow
        label="额外描述"
        value=""
        active={false}
        onActivate={vi.fn()}
        onChange={vi.fn()}
      />,
    )
    expect(screen.getByText('点击添加额外描述…')).toBeInTheDocument()
    expect(screen.queryByText('点击添加额外描述描述…')).not.toBeInTheDocument()
  })

  it('普通槽位仍显示「点击添加{label}描述…」', () => {
    render(
      <PromptSlotRow
        label="人脸"
        value=""
        active={false}
        onActivate={vi.fn()}
        onChange={vi.fn()}
      />,
    )
    expect(screen.getByText('点击添加人脸描述…')).toBeInTheDocument()
  })

  it('展开态优先使用自定义 placeholder，默认兜底为「输入{label}描述…」', () => {
    const { rerender } = render(
      <PromptSlotRow
        label="风格"
        value=""
        active
        placeholder="例如：写实人像摄影、胶片质感"
        onActivate={vi.fn()}
        onChange={vi.fn()}
      />,
    )
    expect(screen.getByPlaceholderText('例如：写实人像摄影、胶片质感')).toBeInTheDocument()

    rerender(
      <PromptSlotRow
        label="场景"
        value=""
        active
        onActivate={vi.fn()}
        onChange={vi.fn()}
      />,
    )
    expect(screen.getByPlaceholderText('输入场景描述…')).toBeInTheDocument()
  })

  it('输入内容后回调 onChange', () => {
    const onChange = vi.fn()
    render(
      <PromptSlotRow
        label="场景"
        value=""
        active
        onActivate={vi.fn()}
        onChange={onChange}
      />,
    )
    fireEvent.change(screen.getByPlaceholderText('输入场景描述…'), { target: { value: '海边' } })
    expect(onChange).toHaveBeenCalledWith('海边')
  })
})
