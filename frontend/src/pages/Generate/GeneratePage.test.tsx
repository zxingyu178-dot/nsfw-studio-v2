import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import GeneratePage from './GeneratePage'
import { __resetLayoutForTest } from './workbench/workbenchLayout'

// 无后端环境：让所有 API 请求快速失败，组件自身已做错误兜底。
beforeEach(() => {
  __resetLayoutForTest()
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

describe('GeneratePage 工作台骨架', () => {
  it('挂载 WorkbenchBar 与三栏（Prompt Console / Canvas / 参数）', async () => {
    renderPage()
    // WorkbenchBar 模式切换
    expect(screen.getByText('文生图')).toBeInTheDocument()
    expect(screen.getByText('图片生成')).toBeInTheDocument()
    // 左栏 Prompt Console、右栏 Inspector 标题；中栏 Canvas 无标题（Canvas First）
    expect(screen.getByRole('heading', { name: 'PROMPT' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '参数' })).toBeInTheDocument()
    // 底部任务坞存在
    expect(document.querySelector('[data-testid="task-dock"]')).not.toBeNull()
  })

  it('提交按钮存在（拆分生成主操作）', () => {
    renderPage()
    const buttons = screen.getAllByRole('button', { name: /生成/ })
    expect(buttons.length).toBeGreaterThan(0)
  })
})

describe('GeneratePage Phase 0.17.1：三栏可收起', () => {
  it('左栏可收起为竖栏并可再展开', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: 'PROMPT' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '收起 Prompt 栏' }))
    // 收起后内容不再挂载，只保留展开竖栏
    expect(screen.queryByRole('heading', { name: 'PROMPT' })).toBeNull()
    const expand = screen.getByRole('button', { name: '展开Prompt 栏' })
    expect(expand).toBeInTheDocument()

    fireEvent.click(expand)
    expect(screen.getByRole('heading', { name: 'PROMPT' })).toBeInTheDocument()
  })

  it('右栏可收起为竖栏并可再展开', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: '参数' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '收起参数栏' }))
    expect(screen.queryByRole('heading', { name: '参数' })).toBeNull()
    const expand = screen.getByRole('button', { name: '展开参数栏' })

    fireEvent.click(expand)
    expect(screen.getByRole('heading', { name: '参数' })).toBeInTheDocument()
  })

  it('收起状态写入 CSS 变量，宽度让给 Canvas（collapse 后 --left-w 为 44px）', () => {
    const { container } = renderPage()
    const columns = container.querySelector('.wb4-columns') as HTMLElement
    expect(columns.style.getPropertyValue('--left-w')).toBe('320px')

    fireEvent.click(screen.getByRole('button', { name: '收起 Prompt 栏' }))
    expect(columns.style.getPropertyValue('--left-w')).toBe('44px')
  })
})


