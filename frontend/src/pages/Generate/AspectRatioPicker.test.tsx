/**
 * AspectRatioPicker 外部状态同步（§4）：
 * - 初始挂载即按 width/height 回选画幅与档位（deriveTier）；
 * - 外部 width/height 变化（Recipe hydrate / History restore / 图片→Workbench）后，
 *   UI 高亮与自定义输入跟随派生值，且派生一致时不重复 set（无 effect 循环）；
 * - 自定义输入聚焦编辑期间不被外部回灌打断，失焦后对齐外部值。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AspectRatioPicker } from './AspectRatioPicker'

function setup(initialWidth = 1024, initialHeight = 1024) {
  const onSizeChange = vi.fn()
  const utils = render(
    <AspectRatioPicker width={initialWidth} height={initialHeight} onSizeChange={onSizeChange} />,
  )
  return { ...utils, onSizeChange }
}

function tile(name: string): HTMLElement {
  return screen.getByRole('button', { name })
}

describe('AspectRatioPicker 外部状态同步', () => {
  it('挂载 1024×1024 → 选中 1:1 / 标准档', () => {
    setup(1024, 1024)
    expect(tile('1:1')).toHaveAttribute('aria-pressed', 'true')
    expect(tile('9:16')).toHaveAttribute('aria-pressed', 'false')
    expect(tile('标准')).toHaveAttribute('aria-pressed', 'true')
    expect(tile('高清')).toHaveAttribute('aria-pressed', 'false')
    expect(tile('自定义')).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByTestId('size-current')).toHaveTextContent('当前 1024 × 1024')
  })

  it('挂载 1920×1088 → 初始即回选 16:9 / 高清档', () => {
    setup(1920, 1088)
    expect(tile('16:9')).toHaveAttribute('aria-pressed', 'true')
    expect(tile('1:1')).toHaveAttribute('aria-pressed', 'false')
    expect(tile('高清')).toHaveAttribute('aria-pressed', 'true')
    expect(tile('标准')).toHaveAttribute('aria-pressed', 'false')
  })

  it('外部 hydrate：1024×1024 → 1088×1920 → 9:16 / 高清档跟随', () => {
    const { rerender } = setup(1024, 1024)
    expect(tile('1:1')).toHaveAttribute('aria-pressed', 'true')

    rerender(<AspectRatioPicker width={1088} height={1920} onSizeChange={vi.fn()} />)
    expect(tile('9:16')).toHaveAttribute('aria-pressed', 'true')
    expect(tile('1:1')).toHaveAttribute('aria-pressed', 'false')
    expect(tile('高清')).toHaveAttribute('aria-pressed', 'true')
    expect(tile('标准')).toHaveAttribute('aria-pressed', 'false')
  })

  it('外部 hydrate：1088×1920 → 1920×1088 → 16:9 / 高清档', () => {
    const { rerender } = setup(1088, 1920)
    expect(tile('9:16')).toHaveAttribute('aria-pressed', 'true')

    rerender(<AspectRatioPicker width={1920} height={1088} onSizeChange={vi.fn()} />)
    expect(tile('16:9')).toHaveAttribute('aria-pressed', 'true')
    expect(tile('9:16')).toHaveAttribute('aria-pressed', 'false')
    expect(tile('高清')).toHaveAttribute('aria-pressed', 'true')
  })

  it('自定义尺寸 hydrate → 切到自定义档并回填 custom 输入', () => {
    const { rerender } = setup(1024, 1024)
    rerender(<AspectRatioPicker width={832} height={1216} onSizeChange={vi.fn()} />)
    expect(tile('自定义')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('textbox', { name: '宽度' })).toHaveValue('832')
    expect(screen.getByRole('textbox', { name: '高度' })).toHaveValue('1216')
  })

  it('custom 输入聚焦编辑期间不被外部 hydrate 打断，失焦后对齐外部值', () => {
    const { rerender } = setup(832, 1216)
    const widthInput = screen.getByRole('textbox', { name: '宽度' })
    expect(widthInput).toHaveValue('832')

    // 用户聚焦宽输入（正在编辑）
    fireEvent.focus(widthInput)
    // 外部 Recipe/History 在编辑期间改写 store 到 1280×1792
    rerender(<AspectRatioPicker width={1280} height={1792} onSizeChange={vi.fn()} />)
    // 编辑中：输入不被回灌，仍显示 832
    expect(widthInput).toHaveValue('832')
    expect(screen.getByRole('textbox', { name: '高度' })).toHaveValue('1216')

    // 失焦 → 对齐外部值
    fireEvent.blur(widthInput)
    expect(screen.getByRole('textbox', { name: '宽度' })).toHaveValue('1280')
    expect(screen.getByRole('textbox', { name: '高度' })).toHaveValue('1792')
  })

  it('派生一致时重复 setProps 不产生额外 onSizeChange（effect 幂等守卫）', () => {
    const { onSizeChange } = setup(1024, 1024)
    expect(onSizeChange).not.toHaveBeenCalled()
    // 组件内 effect 只回选本地高亮，不回写 store
  })
})
