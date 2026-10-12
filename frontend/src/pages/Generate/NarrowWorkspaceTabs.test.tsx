/**
 * Phase 0.13：<1024 窄屏 Workspace Tabs 契约
 *
 * 窄屏不纵向展开，改为固定高度 tab（Prompt | 预览 | 配置），一次一个 pane。
 * 宽屏三栏时 tab 栏由 CSS 隐藏；本测试锁定 tab 结构与切换行为。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import GeneratePage from './GeneratePage'

// 无后端环境：让所有 API 请求快速失败，组件自身已做错误兜底。
beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.reject(new Error('no backend')))
  )
})

function renderPage() {
  return render(
    <MemoryRouter>
      <GeneratePage />
    </MemoryRouter>
  )
}

describe('NarrowWorkspaceTabs：窄屏单栏 tab 切换', () => {
  it('渲染 Prompt / 预览 / 配置 三个 workspace tab', () => {
    const { container } = renderPage()
    const tabs = container.querySelector('.generate__tabs')
    expect(tabs, '.generate__tabs 容器未渲染').toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Prompt' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '预览' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '配置' })).toBeInTheDocument()
  })

  it('默认选中 Prompt，root 带 generate--tab-prompt', () => {
    const { container } = renderPage()
    expect(container.firstElementChild!.className).toContain('generate--tab-prompt')
    expect(screen.getByRole('tab', { name: '预览' }).getAttribute('aria-selected')).toBe('false')
    expect(screen.getByRole('tab', { name: 'Prompt' }).getAttribute('aria-selected')).toBe('true')
  })

  it('点击“配置”切换 root class 为 generate--tab-settings', () => {
    const { container } = renderPage()
    fireEvent.click(screen.getByRole('tab', { name: '配置' }))
    expect(container.firstElementChild!.className).toContain('generate--tab-settings')
    expect(screen.getByRole('tab', { name: '配置' }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByRole('tab', { name: 'Prompt' }).getAttribute('aria-selected')).toBe('false')
  })

  it('三个 pane 包裹层均渲染（.generate__pane--prompt/preview/settings）', () => {
    const { container } = renderPage()
    expect(container.querySelector('.generate__pane--prompt')).toBeTruthy()
    expect(container.querySelector('.generate__pane--preview')).toBeTruthy()
    expect(container.querySelector('.generate__pane--settings')).toBeTruthy()
  })
})
