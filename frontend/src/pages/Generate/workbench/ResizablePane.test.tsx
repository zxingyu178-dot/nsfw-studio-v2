/**
 * ResizablePane 拖拽侧栏交互与无障碍（v0.15 Task 1）。
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ResizablePane } from './ResizablePane'

function renderPane(side: 'left' | 'right', width: number) {
  const onChange = vi.fn()
  const onReset = vi.fn()
  render(
    <ResizablePane
      side={side}
      width={width}
      min={280}
      max={420}
      label={`${side} 栏宽度`}
      onChange={onChange}
      onReset={onReset}
    >
      <div>pane-content</div>
    </ResizablePane>,
  )
  return { onChange, onReset }
}

describe('ResizablePane 无障碍与键盘', () => {
  it('渲染 role=separator / aria-orientation=vertical / aria-valuenow 与 min/max', () => {
    renderPane('left', 340)
    const sep = screen.getByRole('separator') as HTMLElement
    expect(sep.getAttribute('aria-orientation')).toBe('vertical')
    expect(sep.getAttribute('aria-valuenow')).toBe('340')
    expect(sep.getAttribute('aria-valuemin')).toBe('280')
    expect(sep.getAttribute('aria-valuemax')).toBe('420')
  })

  it('左栏：ArrowRight +8、Shift+ArrowRight +24、ArrowLeft -8（clamp）', () => {
    const { onChange } = renderPane('left', 340)
    const sep = screen.getByRole('separator')
    fireEvent.keyDown(sep, { key: 'ArrowRight' })
    expect(onChange).toHaveBeenLastCalledWith(348)
    fireEvent.keyDown(sep, { key: 'ArrowRight', shiftKey: true })
    expect(onChange).toHaveBeenLastCalledWith(364)
    fireEvent.keyDown(sep, { key: 'ArrowLeft' })
    expect(onChange).toHaveBeenLastCalledWith(332)
  })

  it('右栏方向取反：ArrowLeft 变宽（+8）', () => {
    const { onChange } = renderPane('right', 300)
    const sep = screen.getByRole('separator')
    fireEvent.keyDown(sep, { key: 'ArrowLeft' })
    expect(onChange).toHaveBeenLastCalledWith(308)
  })

  it('Home 键复位（调用 onReset）', () => {
    const { onReset } = renderPane('left', 380)
    fireEvent.keyDown(screen.getByRole('separator'), { key: 'Home' })
    expect(onReset).toHaveBeenCalledTimes(1)
  })

  it('双击手柄复位', () => {
    const { onReset } = renderPane('left', 380)
    fireEvent.doubleClick(screen.getByRole('separator'))
    expect(onReset).toHaveBeenCalledTimes(1)
  })
})
