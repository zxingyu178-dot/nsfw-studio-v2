import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

// ===== Mock workbenchStore =====
const mockUseWorkbench = vi.fn()
const mockSetCount = vi.fn()

vi.mock('../../../stores/workbenchStore', () => ({
  useWorkbench: (...args: unknown[]) => mockUseWorkbench(...args),
  hasUpscaleModule: vi.fn(() => false),
  isImageCapablePrimary: vi.fn(() => true),
  isImageStartModule: vi.fn(() => false),
  setCount: (...args: unknown[]) => mockSetCount(...args),
  setPrimaryModule: vi.fn(),
  setPrimaryModuleConfig: vi.fn(),
  setSeed: vi.fn(),
  setSize: vi.fn(),
  setUpscaleEnabled: vi.fn(),
  MODULE_LABEL: {},
}))

// ===== Mock jobStore：引擎离线 =====
vi.mock('../../../stores/jobStore', () => ({
  useJobStore: vi.fn(() => ({
    engine: null,
    engineLoaded: true,
    queue: { worker: { running: false, queue_paused: false }, running: null, queued: [], paused: [] },
    submitting: false,
    busyJobId: null,
    lastError: null,
  })),
  activeJob: vi.fn(() => null),
}))

import { GenerationControls } from './GenerationControls'

function state(count = 1) {
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
    count,
    seedMode: 'random' as const,
    seed: null,
    workflowModules: [{ module_id: 'basic_generate', config: {} }],
    moduleCatalog: [],
  }
}

beforeEach(() => vi.clearAllMocks())

describe('输出数量自由输入（权威口径 1–64）', () => {
  it('渲染数字输入框与常用档 chips，并显示范围提示', () => {
    mockUseWorkbench.mockReturnValue(state(1))
    render(<GenerationControls />)
    expect(screen.getByRole('textbox', { name: '数量' })).toBeInTheDocument()
    expect(screen.getByText('1–64 张')).toBeInTheDocument()
    for (const n of [1, 2, 4, 6, 8]) {
      expect(screen.getByRole('button', { name: String(n) })).toBeInTheDocument()
    }
  })

  it('可自由输入 3 / 5 / 10，blur 后提交 setCount', () => {
    mockUseWorkbench.mockReturnValue(state(1))
    render(<GenerationControls />)
    const input = screen.getByRole('textbox', { name: '数量' })

    fireEvent.change(input, { target: { value: '3' } })
    fireEvent.blur(input)
    expect(mockSetCount).toHaveBeenLastCalledWith(3)

    fireEvent.change(input, { target: { value: '5' } })
    fireEvent.blur(input)
    expect(mockSetCount).toHaveBeenLastCalledWith(5)

    fireEvent.change(input, { target: { value: '10' } })
    fireEvent.blur(input)
    expect(mockSetCount).toHaveBeenLastCalledWith(10)
  })

  it('常用档 chip 点击直接 setCount(n)', () => {
    mockUseWorkbench.mockReturnValue(state(1))
    render(<GenerationControls />)
    fireEvent.click(screen.getByRole('button', { name: '4' }))
    expect(mockSetCount).toHaveBeenLastCalledWith(4)
  })

  it('越界输入在 blur 时钳制到 1–64；非数字输入不触发提交', () => {
    mockUseWorkbench.mockReturnValue(state(5))
    render(<GenerationControls />)
    const input = screen.getByRole('textbox', { name: '数量' })

    fireEvent.change(input, { target: { value: '0' } })
    fireEvent.blur(input)
    expect(mockSetCount).toHaveBeenLastCalledWith(1)

    fireEvent.change(input, { target: { value: '65' } })
    fireEvent.blur(input)
    expect(mockSetCount).toHaveBeenLastCalledWith(64)

    fireEvent.change(input, { target: { value: '100' } })
    fireEvent.blur(input)
    expect(mockSetCount).toHaveBeenLastCalledWith(64)

    // NumberStepper 契约：非数字输入 blur 后还原为当前值，不触发 setCount（不跳到 1）
    const callsBefore = mockSetCount.mock.calls.length
    fireEvent.change(input, { target: { value: 'abc' } })
    fireEvent.blur(input)
    expect(mockSetCount.mock.calls.length).toBe(callsBefore)
  })
})
