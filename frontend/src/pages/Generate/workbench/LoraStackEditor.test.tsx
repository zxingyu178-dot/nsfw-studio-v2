import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { LoraStackEditor } from './LoraStackEditor'

const options = [{ value: 'a.safetensors', label: 'LoRA A', strength: 0.6 }]

describe('LoraStackEditor 推荐强度', () => {
  it('手动调整后显示推荐强度与恢复入口', () => {
    const onChange = vi.fn()
    render(
      <LoraStackEditor
        loras={[{ name: 'a.safetensors', strength_model: 1, strength_clip: 1 }]}
        options={options}
        onChange={onChange}
      />,
    )
    expect(screen.getByText(/推荐强度 0\.6/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '恢复推荐' }))
    expect(onChange).toHaveBeenCalledWith([
      { name: 'a.safetensors', strength_model: 0.6, strength_clip: 0.6 },
    ])
  })

  it('当前强度等于推荐值时只显示提示', () => {
    render(
      <LoraStackEditor
        loras={[{ name: 'a.safetensors', strength_model: 0.6, strength_clip: 0.6 }]}
        options={options}
        onChange={() => {}}
      />,
    )
    expect(screen.getByText(/推荐强度 0\.6/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '恢复推荐' })).toBeNull()
  })

  it('未登记推荐强度的 LoRA 不占位', () => {
    render(
      <LoraStackEditor
        loras={[{ name: 'b.safetensors', strength_model: 1, strength_clip: 1 }]}
        options={[{ value: 'b.safetensors', label: 'LoRA B' }]}
        onChange={() => {}}
      />,
    )
    expect(screen.queryByText(/推荐强度/)).toBeNull()
  })
})
