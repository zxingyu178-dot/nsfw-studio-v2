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
  it('挂载模式栏与三栏（编辑 / 结果 / 参数）', async () => {
    renderPage()
    // 模式栏（UI-1 前为 tablist 结构）
    expect(screen.getByText('文生图')).toBeInTheDocument()
    expect(screen.getByText('图片生成')).toBeInTheDocument()
    // 三栏标题
    expect(screen.getByText('Prompt 编辑')).toBeInTheDocument()
    expect(screen.getByText('预览')).toBeInTheDocument()
    expect(screen.getByText('生成配置')).toBeInTheDocument()
  })

  it('提交按钮存在（主操作）', () => {
    renderPage()
    const buttons = screen.getAllByRole('button', { name: '生成' })
    expect(buttons.length).toBeGreaterThan(0)
  })
})
