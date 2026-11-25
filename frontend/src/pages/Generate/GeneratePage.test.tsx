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
  it('挂载 WorkbenchBar 与双栏（Prompt Console / 参数），不重复渲染 Canvas', async () => {
    renderPage()
    // WorkbenchBar 模式切换（默认收纳，点开后才显示图生图选项）
    const modeTrigger = screen.getByRole('button', { name: /文生图/ })
    fireEvent.click(modeTrigger)
    expect(screen.getByRole('menuitemradio', { name: /文生图/ })).toBeInTheDocument()
    expect(screen.getByRole('menuitemradio', { name: /图片生成/ })).toBeInTheDocument()
    // 创作页只承担输入与参数，实时结果统一回首页查看。
    expect(screen.getByRole('heading', { name: 'PROMPT' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '参数' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '查看实时预览' })).toHaveAttribute('href', '/')
    expect(screen.queryByLabelText('生成结果画布')).not.toBeInTheDocument()
    // 底部任务坞存在
    expect(document.querySelector('[data-testid="task-dock"]')).not.toBeNull()
  })

  it('提交按钮存在（拆分生成主操作）', () => {
    renderPage()
    const buttons = screen.getAllByRole('button', { name: /生成/ })
    expect(buttons.length).toBeGreaterThan(0)
  })
})

describe('GeneratePage：双栏布局偏好兼容', () => {
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

  it('收起状态继续写入既有 CSS 变量（兼容已发布布局偏好）', () => {
    const { container } = renderPage()
    const columns = container.querySelector('.wb4-columns') as HTMLElement
    // Phase 0.18 对齐 DESIGN.md：左生成控制台默认 280px。
    expect(columns.style.getPropertyValue('--left-w')).toBe('280px')

    fireEvent.click(screen.getByRole('button', { name: '收起 Prompt 栏' }))
    expect(columns.style.getPropertyValue('--left-w')).toBe('44px')
  })
})


