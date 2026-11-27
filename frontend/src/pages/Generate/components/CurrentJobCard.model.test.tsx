import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
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

function runningJob(overrides: Partial<JobDTO> = {}): JobDTO {
  return {
    id: 'job_ai_model',
    source: 'agent',
    status: 'RUNNING',
    positive_prompt_snapshot: 'a cat',
    requested_count: 2,
    completed_count: 0,
    module_id: 'anime_generate',
    workflow_snapshot: {
      modules: [{ module_id: 'anime_generate', config: { model: 'NoobAI-XL-v1.1.safetensors' } }],
    },
    items: [],
    stages: [],
    error_type: null,
    error_message: null,
    created_at: '',
    updated_at: '',
    started_at: '',
    finished_at: '',
    cancel_requested: false,
    pause_requested: false,
    ...overrides,
  } as unknown as JobDTO
}

describe('CurrentJobCard 底模与来源', () => {
  it('Agent 任务显示底模短名、AI 提交与中文工作流名', () => {
    render(<CurrentJobCard job={runningJob()} busy={false} />)
    expect(screen.getByText('底模 NoobAI-XL-v1.1')).toBeInTheDocument()
    expect(screen.getByText('AI 提交')).toBeInTheDocument()
    expect(screen.getByText('动漫生成')).toBeInTheDocument()
  })

  it('Web / 无快照任务不显示底模与 AI 标识', () => {
    render(<CurrentJobCard job={runningJob({ source: 'web', workflow_snapshot: undefined })} busy={false} />)
    expect(screen.queryByText(/底模/)).toBeNull()
    expect(screen.queryByText('AI 提交')).toBeNull()
  })
})
