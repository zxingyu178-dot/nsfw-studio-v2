/**
 * ActionDock 轻量测试：渲染为 toolbar，承接 IconButton 子项。
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ActionDock } from './ActionDock'
import { IconButton } from './IconButton'
import { IconClose, IconInfo, IconPrev } from './icons'

describe('ActionDock', () => {
  it('渲染为 toolbar 并包含子 IconButton', () => {
    render(
      <ActionDock label="图片动作坞">
        <IconButton icon={<IconPrev />} label="上一张" tooltip={null} />
        <IconButton icon={<IconClose />} label="关闭" tooltip={null} />
        <IconButton icon={<IconInfo />} label="信息" tooltip={null} />
      </ActionDock>,
    )
    const dock = screen.getByRole('toolbar', { name: '图片动作坞' })
    expect(dock).toBeInTheDocument()
    expect(screen.getAllByRole('button')).toHaveLength(3)
  })
})
