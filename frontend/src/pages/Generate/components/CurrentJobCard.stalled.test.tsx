import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { jobErrorText } from '../../../utils/jobProgress'
import { CurrentJobCard } from './CurrentJobCard'
import type { JobDTO } from '../../../types/workbench'

vi.mock('../../../components/ui', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../../components/ui')
  return {
    ...actual,
    ElapsedTimer: () => <span data-testid="elapsed" />,
    ProgressBar: ({ ariaLabel }: { ariaLabel: string }) => <div role="progressbar" aria-label={ariaLabel} />,
  }
})

function stalledJob(): JobDTO {
  return {
    id: 'job_stalled',
    positive_prompt_snapshot: 'a cat',
    requested_count: 4,
    completed_count: 1,
    status: 'FAILED',
    module_id: 'base',
    items: [
      {
        id: 'it1', job_id: 'job_stalled', item_index: 0, status: 'COMPLETED', progress: 1,
        current_stage: 'decode', seed: 101, created_at: '', updated_at: '',
      },
      {
        id: 'it2', job_id: 'job_stalled', item_index: 1, status: 'FAILED', progress: 0.12,
        current_stage: 'decode', seed: 102, created_at: '', updated_at: '',
        error_type: 'ENGINE_STALLED',
        error_message: 'progress stayed 0 for 180s',
      },
    ],
    stages: [],
    error_type: 'ENGINE_STALLED',
    error_message: 'progress stayed 0 for 180s',
    created_at: '', updated_at: '', started_at: '', finished_at: '',
    cancel_requested: false, pause_requested: false,
  } as unknown as JobDTO
}

describe('v0.13.2 ENGINE_STALLED 可读文案', () => {
  it('jobErrorText：ENGINE_STALLED 翻成中文人话，不外露机器码', () => {
    expect(jobErrorText('ENGINE_STALLED', 'progress stayed 0 for 180s')).toBe(
      '引擎长时间无进度，已自动停止并释放队列头，可重试该任务。',
    )
  })

  it('jobErrorText：其他错误保留"类型：详情"', () => {
    expect(jobErrorText('ENGINE_DISCONNECTED', 'boom')).toBe('ENGINE_DISCONNECTED：boom')
  })

  it('CurrentJobCard：失败任务显示可读中文，不出现机器码堆叠', () => {
    render(<CurrentJobCard job={stalledJob()} busy={false} />)
    const box = screen.getByTestId('job-error-text')
    expect(box.textContent).toContain('引擎长时间无进度')
    expect(box.textContent).not.toContain('ENGINE_STALLED：')
  })
})
