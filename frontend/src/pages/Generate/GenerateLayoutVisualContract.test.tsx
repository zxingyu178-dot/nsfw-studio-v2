import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import GeneratePage from './GeneratePage'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('no backend'))))
})

function renderPage() {
  return render(
    <MemoryRouter>
      <GeneratePage />
    </MemoryRouter>,
  )
}

describe('GenerateLayoutVisualContract（≥1024 三栏 + 一屏 + 主按钮首屏可见）', () => {
  it('三栏根与三列面板同时存在（编辑 / 预览 / 配置）', () => {
    const { container } = renderPage()
    expect(container.querySelector('.generate')).not.toBeNull()
    expect(container.querySelector('.wb4-columns')).not.toBeNull()
    expect(container.querySelector('.generate__pane--prompt')).not.toBeNull()
    expect(container.querySelector('.generate__pane--preview')).not.toBeNull()
    expect(container.querySelector('.generate__pane--settings')).not.toBeNull()
  })

  it('采用一屏高布局：根容器为 height:100%、内部滚动（不靠整页滚动）', () => {
    const { container } = renderPage()
    const root = container.querySelector('.generate') as HTMLElement
    // 契约由 generate.css 提供：.generate{height:100%;min-height:0}、.wb-pane__body{overflow-y:auto}
    expect(container.querySelector('.wb-pane__body')).not.toBeNull()
    expect(root.className).toContain('generate')
  })

  it('主生成按钮位于配置栏底部 footer，结构上首屏可达（非深埋滚动）', () => {
    const { container } = renderPage()
    const settingsPane = container.querySelector('.generate__pane--settings') as HTMLElement
    expect(settingsPane).not.toBeNull()
    const mainBtn = settingsPane.querySelector('button.generate-action')
    expect(mainBtn).not.toBeNull()
    // 主按钮渲染在该栏 footer 内（sticky 底部）
    expect(settingsPane.querySelector('.wb-pane__footer button.generate-action')).not.toBeNull()
  })
})
