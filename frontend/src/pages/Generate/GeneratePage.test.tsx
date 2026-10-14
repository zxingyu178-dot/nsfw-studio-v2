import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
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

describe('GeneratePage 工作台骨架', () => {
  it('挂载 WorkbenchBar 与三栏（Prompt Console / Canvas / 参数）', async () => {
    renderPage()
    // WorkbenchBar 模式切换
    expect(screen.getByText('文生图')).toBeInTheDocument()
    expect(screen.getByText('图片生成')).toBeInTheDocument()
    // 左栏 Prompt Console、右栏 Inspector 标题；中栏 Canvas 无标题（Canvas First）
    expect(screen.getByRole('heading', { name: 'Prompt 编辑' })).toBeInTheDocument()
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
