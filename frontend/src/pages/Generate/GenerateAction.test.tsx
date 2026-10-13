import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { GenerateAction } from './components/GenerateAction'

vi.mock('../../stores/workbenchStore', () => ({
  useWorkbench: vi.fn(),
  isImageCapablePrimary: vi.fn(() => true),
  snapshotFromState: vi.fn(() => ({})),
}))
vi.mock('../../stores/jobStore', () => ({
  useJobStore: vi.fn(),
  submitGeneration: vi.fn(() => Promise.resolve(null)),
}))

import { useWorkbench } from '../../stores/workbenchStore'
import { useJobStore } from '../../stores/jobStore'

const readyState = {
  promptMode: 'full' as const,
  fullPrompt: 'a cyberpunk portrait',
  structured: {} as Record<string, string>,
  count: 1,
  mode: 'text' as const,
  inputImages: [] as unknown[],
  negativePrompt: '',
}
const readyJob = {
  engineLoaded: false,
  engine: null,
  submitting: false,
  busyJobId: null as string | null,
  lastError: null as string | null,
}

beforeEach(() => {
  vi.mocked(useWorkbench).mockReturnValue(readyState as never)
  vi.mocked(useJobStore).mockReturnValue(readyJob as never)
})

describe('GenerateAction 主按钮', () => {
  it('默认可用，文案为「生成」（count=1）', () => {
    render(<GenerateAction imageGenAvailable={true} />)
    const btn = screen.getByRole('button', { name: '生成' })
    expect(btn).toBeEnabled()
  })

  it('count>1 时文案为「生成 N 张」', () => {
    vi.mocked(useWorkbench).mockReturnValue({ ...readyState, count: 4 } as never)
    render(<GenerateAction imageGenAvailable={true} />)
    expect(screen.getByRole('button', { name: '生成 4 张' })).toBeInTheDocument()
  })

  it('submitting 时进入 loading：显示细线、文案为「提交中…」且禁用', () => {
    vi.mocked(useJobStore).mockReturnValue({ ...readyJob, submitting: true } as never)
    render(<GenerateAction imageGenAvailable={true} />)
    expect(screen.getByRole('button', { name: '提交中…' })).toBeDisabled()
    expect(document.querySelector('.generate-action__line')).not.toBeNull()
  })

  it('Gate 阻断时不仅禁用按钮，还可见显示原因（如未填 Prompt）', () => {
    vi.mocked(useWorkbench).mockReturnValue({ ...readyState, fullPrompt: '' } as never)
    render(<GenerateAction imageGenAvailable={true} />)
    expect(screen.getByText('请先填写 Prompt')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '生成' })).toBeDisabled()
  })
})
