import { StrictMode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ResumeInterruptedPrompt } from './ResumeInterruptedPrompt'
import { ToastProvider } from './ui'
import { ApiRequestError, jobApi } from '../api/client'

vi.mock('../api/client', () => ({
  ApiRequestError: class extends Error {
    constructor(_code: string, message: string) {
      super(message)
    }
  },
  jobApi: {
    list: vi.fn(),
    resumeInterrupted: vi.fn(),
  },
}))

function renderPrompt() {
  return render(
    <ToastProvider>
      <ResumeInterruptedPrompt />
    </ToastProvider>,
  )
}

describe('ResumeInterruptedPrompt', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.clearAllMocks()
  })

  it('检测到 2 个中断任务后弹窗，继续全部并显示成功提示', async () => {
    vi.mocked(jobApi.list).mockResolvedValue({ items: [], total: 2, limit: 1, offset: 0 })
    vi.mocked(jobApi.resumeInterrupted).mockResolvedValue({
      requeued: ['job_1'],
      resumed: [{ parent_job_id: 'job_2', child_job_id: 'job_3' }],
      skipped: [],
      errors: [],
      requeued_count: 1,
      resumed_count: 1,
      remaining_images: 3,
    })

    renderPrompt()

    expect(await screen.findByRole('dialog', { name: '继续中断的生成任务？' })).toBeInTheDocument()
    expect(screen.getByText(/检测到 2 个中断任务/)).toBeInTheDocument()
    expect(jobApi.list).toHaveBeenCalledWith({ status: 'INTERRUPTED', limit: 1 })

    fireEvent.click(screen.getByRole('button', { name: '一键继续全部' }))

    await waitFor(() => expect(jobApi.resumeInterrupted).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('已恢复 2 个任务，剩余 3 张')).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: '继续中断的生成任务？' })).not.toBeInTheDocument()
    expect(sessionStorage.getItem('resume-interrupted-dismissed')).toBe('1')
  })

  it('稍后关闭且不恢复，并在当前会话记住选择', async () => {
    vi.mocked(jobApi.list).mockResolvedValue({ items: [], total: 2, limit: 1, offset: 0 })

    const { unmount } = renderPrompt()
    await screen.findByRole('dialog', { name: '继续中断的生成任务？' })
    fireEvent.click(screen.getByRole('button', { name: '稍后' }))

    expect(jobApi.resumeInterrupted).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog', { name: '继续中断的生成任务？' })).not.toBeInTheDocument()
    expect(sessionStorage.getItem('resume-interrupted-dismissed')).toBe('1')

    unmount()
    renderPrompt()
    await waitFor(() => expect(jobApi.list).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('dialog', { name: '继续中断的生成任务？' })).not.toBeInTheDocument()
  })

  it('没有中断任务时不弹窗', async () => {
    vi.mocked(jobApi.list).mockResolvedValue({ items: [], total: 0, limit: 1, offset: 0 })

    renderPrompt()

    await waitFor(() => expect(jobApi.list).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('dialog', { name: '继续中断的生成任务？' })).not.toBeInTheDocument()
  })

  it('StrictMode 重放 effect 时只检测一次且仍消费检测结果', async () => {
    let resolveList!: (value: { items: never[]; total: number; limit: number; offset: number }) => void
    vi.mocked(jobApi.list).mockReturnValue(new Promise((resolve) => { resolveList = resolve }) as never)

    render(
      <StrictMode>
        <ToastProvider>
          <ResumeInterruptedPrompt />
        </ToastProvider>
      </StrictMode>,
    )

    expect(jobApi.list).toHaveBeenCalledTimes(1)
    resolveList({ items: [], total: 2, limit: 1, offset: 0 })

    expect(await screen.findByRole('dialog', { name: '继续中断的生成任务？' })).toBeInTheDocument()
  })

  it('恢复失败时展示 API 错误并保留弹窗，允许再次提交成功', async () => {
    vi.mocked(jobApi.list).mockResolvedValue({ items: [], total: 1, limit: 1, offset: 0 })
    vi.mocked(jobApi.resumeInterrupted)
      .mockRejectedValueOnce(new ApiRequestError('RESUME_FAILED', '服务暂时不可用，请重试', 503))
      .mockResolvedValueOnce({
        requeued: [],
        resumed: [{ parent_job_id: 'job_1', child_job_id: 'job_2' }],
        skipped: [],
        errors: [],
        requeued_count: 0,
        resumed_count: 1,
        remaining_images: 2,
      })

    renderPrompt()
    await screen.findByRole('dialog', { name: '继续中断的生成任务？' })

    fireEvent.click(screen.getByRole('button', { name: '一键继续全部' }))
    expect(await screen.findByText('服务暂时不可用，请重试')).toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: '继续中断的生成任务？' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '一键继续全部' }))
    await waitFor(() => expect(jobApi.resumeInterrupted).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('已恢复 1 个任务，剩余 2 张')).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: '继续中断的生成任务？' })).not.toBeInTheDocument()
  })
})
