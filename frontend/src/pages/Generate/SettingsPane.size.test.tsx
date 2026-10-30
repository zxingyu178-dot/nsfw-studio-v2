import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

// ===== Mock workbenchStore：控制 width/height / mode / moduleCatalog =====
const mockUseWorkbench = vi.fn()
const mockSetSize = vi.fn()

vi.mock('../../stores/workbenchStore', () => ({
  useWorkbench: (...args: unknown[]) => mockUseWorkbench(...args),
  hasUpscaleModule: vi.fn(() => false),
  isImageCapablePrimary: vi.fn(() => true),
  isImageStartModule: vi.fn(() => false),
  releaseStatusNotice: vi.fn(() => null),
  textPrimaryCandidates: (catalog: { available?: boolean; input_required?: boolean }[]) =>
    catalog.filter((module) => module.available && !module.input_required),
  setCount: vi.fn(),
  setPrimaryModule: vi.fn(),
  setPrimaryModuleConfig: vi.fn(),
  setSeed: vi.fn(),
  setSize: (...args: unknown[]) => mockSetSize(...args),
  setUpscaleEnabled: vi.fn(),
  snapshotFromState: vi.fn(() => ({})),
}))

// ===== Mock jobStore：无活动任务 =====
vi.mock('../../stores/jobStore', () => ({
  useJobStore: vi.fn(() => ({
    engine: null,
    engineLoaded: true,
    queue: { worker: { running: false, queue_paused: false }, running: null, queued: [], paused: [] },
    submitting: false,
    busyJobId: null,
    lastError: null,
  })),
  activeJob: vi.fn(() => null),
  cancelJob: vi.fn(),
  pauseJob: vi.fn(),
  pauseQueue: vi.fn(),
  reorderQueue: vi.fn(),
  resumeJob: vi.fn(),
  resumeQueue: vi.fn(),
  resumeRemaining: vi.fn(),
  submitGeneration: vi.fn(),
}))

import { SettingsPane } from './SettingsPane'

/** 构造工作台状态（文生图、有 Prompt，使“生成”可用）。 */
function workbenchState(overrides: Partial<Parameters<typeof mockUseWorkbench>[0]> = {}) {
  return {
    promptMode: 'full' as const,
    structured: {},
    fullPrompt: 'a cat',
    negativePrompt: '',
    selectedAssets: {},
    mode: 'text' as const,
    inputImages: [],
    width: 1024,
    height: 1024,
    count: 1,
    seedMode: 'random' as const,
    seed: null,
    workflowModules: [{ module_id: 'basic_generate' }],
    moduleCatalog: [],
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('画幅 + 分辨率预设', () => {
  it('选 9:16 + 高清档 → setSize(1080, 1920)', () => {
    mockUseWorkbench.mockReturnValue(workbenchState())
    render(<SettingsPane imageGenAvailable={true} />)

    fireEvent.click(screen.getByRole('button', { name: '9:16' }))
    expect(mockSetSize).toHaveBeenLastCalledWith(576, 1024)

    fireEvent.click(screen.getByRole('button', { name: '高清' }))
    expect(mockSetSize).toHaveBeenLastCalledWith(1080, 1920)
  })

  it('选 16:9 + 高清档 → setSize(1920, 1080)', () => {
    mockUseWorkbench.mockReturnValue(workbenchState())
    render(<SettingsPane imageGenAvailable={true} />)

    fireEvent.click(screen.getByRole('button', { name: '16:9' }))
    fireEvent.click(screen.getByRole('button', { name: '高清' }))
    expect(mockSetSize).toHaveBeenLastCalledWith(1920, 1080)
  })

  it('自定义：宽高 NumberStepper 提交时 clamp 到 64~4096', () => {
    mockUseWorkbench.mockReturnValue(workbenchState())
    render(<SettingsPane imageGenAvailable={true} />)

    // 初始为预设，不应出现宽高数字输入
    expect(screen.queryByRole('textbox', { name: '宽度' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '自定义' }))
    const widthInput = screen.getByRole('textbox', { name: '宽度' })
    const heightInput = screen.getByRole('textbox', { name: '高度' })
    expect(widthInput).toBeInTheDocument()

    fireEvent.change(widthInput, { target: { value: '5' } })
    fireEvent.blur(widthInput)
    // 5 → clamp 到 64；高度仍为 1024
    expect(mockSetSize).toHaveBeenLastCalledWith(64, 1024)

    fireEvent.change(heightInput, { target: { value: '99999' } })
    fireEvent.blur(heightInput)
    expect(mockSetSize).toHaveBeenLastCalledWith(64, 4096)
  })

  it('size_mode=input（跟随输入图）时隐藏画幅/分辨率', () => {
    mockUseWorkbench.mockReturnValue(
      workbenchState({
        mode: 'image',
        moduleCatalog: [
          {
            module_id: 'basic_generate',
            available: true,
            input_required: true,
            size_mode: 'input',
          },
        ],
      }),
    )
    render(<SettingsPane imageGenAvailable={true} />)

    expect(screen.getByText('跟随输入图（无需设置宽高）')).toBeInTheDocument()
    expect(screen.queryByLabelText('画幅')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('分辨率档位')).not.toBeInTheDocument()
  })

  it('大尺寸出现非阻断慢提示，且“生成”仍可用', () => {
    // 1920×1080 = 2.07M > 1.6M → 慢提示
    mockUseWorkbench.mockReturnValue(workbenchState({ width: 1920, height: 1080 }))
    render(<SettingsPane imageGenAvailable={true} />)

    expect(screen.getByText('该尺寸生成较慢，属正常现象')).toBeInTheDocument()
    const generate = document.querySelector('.wb4-generate__main') as HTMLButtonElement
    expect(generate).toBeTruthy()
    expect(generate).toBeEnabled()
  })
})
