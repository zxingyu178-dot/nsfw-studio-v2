/**
 * v0.15.1：把旧 GenerationControls 的“输出数量 1–64”权威口径迁移到 Workbench 4.0
 * 生产路径（InspectorPanel）——数量控件在右栏参数面板中，min=1/max=64，chips 直接 setCount。
 * 通用钳制/非法输入行为由共享组件 NumberStepper.test.tsx 覆盖，这里只验证生产接线。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const mockSetCount = vi.fn()
const mockUseWorkbench = vi.fn()

vi.mock('../../../stores/workbenchStore', () => ({
  useWorkbench: (...args: unknown[]) => mockUseWorkbench(...args),
  hasUpscaleModule: vi.fn(() => false),
  isImageStartModule: vi.fn(() => false),
  setCount: (...args: unknown[]) => mockSetCount(...args),
  setPrimaryModule: vi.fn(),
  setPrimaryModuleConfig: vi.fn(),
  setSeed: vi.fn(),
  setSize: vi.fn(),
  setUpscaleEnabled: vi.fn(),
  MODULE_LABEL: { basic_generate: '基础生成' },
}))

vi.mock('../AspectRatioPicker', () => ({
  AspectRatioPicker: () => <div data-testid="ratio-picker" />,
}))
vi.mock('./SplitGenerateAction', () => ({
  SplitGenerateAction: () => <div data-testid="split-action" />,
}))
vi.mock('../components/CollapsibleSection', () => ({
  CollapsibleSection: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('../components/ModuleParameterField', () => ({
  ModuleParameterField: () => null,
}))

import { InspectorPanel } from './InspectorPanel'

function workbenchState(count = 1) {
  return {
    promptMode: 'full',
    structured: {},
    fullPrompt: 'a cat',
    mode: 'text',
    inputImages: [],
    width: 1024,
    height: 1024,
    count,
    seedMode: 'random',
    seed: null,
    workflowModules: [{ module_id: 'basic_generate', config: {} }],
    moduleCatalog: [{ module_id: 'basic_generate', title: '基础生成', available: true, input_required: false, parameters: [] }],
  }
}

beforeEach(() => vi.clearAllMocks())

describe('InspectorPanel 数量控件（生产路径，1–64 权威口径）', () => {
  it('渲染数量控件与“1–64 张”范围提示，常用档 chips 为 1/2/4/6/8', () => {
    mockUseWorkbench.mockReturnValue(workbenchState(1))
    render(<InspectorPanel imageGenAvailable={null} />)
    expect(screen.getByRole('textbox', { name: '数量' })).toBeInTheDocument()
    expect(screen.getByText('1–64 张')).toBeInTheDocument()
    for (const n of [1, 2, 4, 6, 8]) {
      expect(screen.getByRole('button', { name: String(n) })).toBeInTheDocument()
    }
  })

  it('chip 点击走生产 setCount；越界 65 由 NumberStepper 钳制到 64', () => {
    mockUseWorkbench.mockReturnValue(workbenchState(5))
    render(<InspectorPanel imageGenAvailable={null} />)
    fireEvent.click(screen.getByRole('button', { name: '4' }))
    expect(mockSetCount).toHaveBeenLastCalledWith(4)

    const input = screen.getByRole('textbox', { name: '数量' }) as HTMLInputElement
    fireEvent.change(input, { target: { value: '65' } })
    fireEvent.blur(input)
    expect(mockSetCount).toHaveBeenLastCalledWith(64)
  })
})
