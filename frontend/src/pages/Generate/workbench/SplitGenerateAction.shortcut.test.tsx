import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { SplitGenerateAction } from './SplitGenerateAction'

vi.mock('../../../stores/workbenchStore', () => ({
  useWorkbench: vi.fn(),
  isImageCapablePrimary: vi.fn(() => true),
  snapshotFromState: vi.fn(() => ({ snapshot: true })),
}))
vi.mock('../../../stores/jobStore', () => ({
  useJobStore: vi.fn(),
  submitGeneration: vi.fn(() => Promise.resolve(null)),
}))

import { useWorkbench } from '../../../stores/workbenchStore'
import { submitGeneration, useJobStore } from '../../../stores/jobStore'

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

function pressCtrlEnter(options: { meta?: boolean } = {}): void {
  fireEvent.keyDown(window, {
    key: 'Enter',
    ctrlKey: !options.meta,
    metaKey: Boolean(options.meta),
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(useWorkbench).mockReturnValue(readyState as never)
  vi.mocked(useJobStore).mockReturnValue(readyJob as never)
  vi.mocked(submitGeneration).mockResolvedValue(null as never)
})

describe('SplitGenerateAction 快捷键', () => {
  it('Ctrl+Enter 提交普通生成', () => {
    render(<SplitGenerateAction imageGenAvailable={true} />)
    pressCtrlEnter()
    expect(submitGeneration).toHaveBeenCalledTimes(1)
    expect(vi.mocked(submitGeneration).mock.calls[0][1]).toBe('normal')
  })

  it('⌘+Enter（macOS）同样生效', () => {
    render(<SplitGenerateAction imageGenAvailable={true} />)
    pressCtrlEnter({ meta: true })
    expect(submitGeneration).toHaveBeenCalledTimes(1)
  })

  it('Gate 阻断（未填 Prompt）时不提交', () => {
    vi.mocked(useWorkbench).mockReturnValue({ ...readyState, fullPrompt: '' } as never)
    render(<SplitGenerateAction imageGenAvailable={true} />)
    expect(screen.getByText('请先填写 Prompt')).toBeInTheDocument()
    pressCtrlEnter()
    expect(submitGeneration).not.toHaveBeenCalled()
  })

  it('提交中（submitting）时不重复提交', () => {
    vi.mocked(useJobStore).mockReturnValue({ ...readyJob, submitting: true } as never)
    render(<SplitGenerateAction imageGenAvailable={true} />)
    pressCtrlEnter()
    expect(submitGeneration).not.toHaveBeenCalled()
  })

  it('按钮 title 提示快捷键', () => {
    const { container } = render(<SplitGenerateAction imageGenAvailable={true} />)
    const button = container.querySelector('.wb4-generate__main')
    expect(button).toHaveAttribute('title', '生成（Ctrl+Enter）')
    expect(button).toHaveAttribute('aria-keyshortcuts', 'Control+Enter')
  })
})
