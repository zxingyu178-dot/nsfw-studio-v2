/**
 * v15 工作台：底模 / LoRA 选择器必须写入 Primary Module config，
 * 且模型候选来自桌面只读接口 /engine/models。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { ModuleCapabilitiesDTO } from '../../../types/workbench'

let mockState: Record<string, unknown>
const setPrimaryModuleConfig = vi.fn()

vi.mock('../../../stores/workbenchStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../stores/workbenchStore')>()
  return {
    ...actual,
    useWorkbench: () => mockState,
    setPrimaryModuleConfig: (...args: unknown[]) => setPrimaryModuleConfig(...args),
  }
})

vi.mock('../AspectRatioPicker', () => ({
  AspectRatioPicker: () => <div data-testid="ratio-picker" />,
}))
vi.mock('../components/ModuleParameterField', () => ({
  ModuleParameterField: () => null,
}))
vi.mock('./SplitGenerateAction', () => ({
  SplitGenerateAction: () => <div data-testid="split-action" />,
}))
vi.mock('../../../api/client', () => ({
  engineRuntimeApi: {
    preflight: vi.fn(),
    models: vi.fn().mockResolvedValue({
      checkpoints: ['NoobAI-XL-v1.1.safetensors'],
      loras: ['cunnyfunky_v5.0_000008.safetensors'],
    }),
  },
}))

import { InspectorPanel } from './InspectorPanel'

const release = {
  registered: true,
  binding_valid: true,
  dependencies_ready: true,
  real_gate_passed: true,
  hardware_status: 'normal',
  default_profile_verified: true,
  ready_to_run: true,
}

const anime: ModuleCapabilitiesDTO = {
  module_id: 'anime_generate',
  module_version: 'v1',
  title: '动漫生成',
  description: '',
  uses_seed: true,
  input_kind: 'text',
  input_required: false,
  input_role: '',
  output_kind: 'original',
  parent_policy: 'independent',
  output_cardinality: 1,
  registered: true,
  available: true,
  provider: 'comfyui',
  binding_version: 'v15',
  unavailable_reason: null,
  is_generative: true,
  allowed_job_kinds: ['generate'],
  release_status: release,
  input_slots: [],
  is_default: true,
  parameters: [
    { name: 'model', type: 'string', required: false, default: '', title: '底模', configurable: true },
    { name: 'loras', type: 'lora_list', required: false, default: [], title: 'LoRA 叠加', configurable: false },
    { name: 'steps', type: 'int', required: false, default: 30, min: 1, max: 100, title: '采样步数', configurable: true },
  ],
}

function renderPanel(config: Record<string, unknown> = {}) {
  mockState = {
    mode: 'text',
    moduleCatalog: [anime],
    workflowModules: [{ module_id: 'anime_generate', config }],
    width: 832,
    height: 1216,
    count: 1,
    seedMode: 'random',
    seed: null,
    promptMode: 'structured',
    structured: {},
    fullPrompt: '',
    negativePrompt: '',
    selectedAssets: {},
    inputImages: [],
    sourcePromptId: null,
    sourcePromptVersionId: null,
    sourceRecipeId: null,
  }
  return render(<InspectorPanel imageGenAvailable={true} />)
}

function chooseOption(buttonName: string, optionText: string) {
  fireEvent.click(screen.getByRole('button', { name: buttonName }))
  fireEvent.click(screen.getByRole('option', { name: optionText }))
}

beforeEach(() => {
  setPrimaryModuleConfig.mockClear()
  mockState = {}
})

describe('InspectorPanel v15 模型与 LoRA', () => {
  it('底模候选来自引擎接口，选择后写入 config.model', async () => {
    renderPanel()
    const modelButton = await screen.findByRole('button', { name: '底模' })
    expect(modelButton.textContent).toContain('绑定默认')
    chooseOption('底模', 'NoobAI-XL-v1.1.safetensors')
    expect(setPrimaryModuleConfig).toHaveBeenCalledWith({ model: 'NoobAI-XL-v1.1.safetensors' })
  })

  it('选择“绑定默认”时删除 config.model（发 undefined，不发送空串）', async () => {
    renderPanel({ model: 'NoobAI-XL-v1.1.safetensors' })
    const modelButton = await screen.findByRole('button', { name: '底模' })
    expect(modelButton.textContent).toContain('NoobAI-XL-v1.1.safetensors')
    chooseOption('底模', '绑定默认')
    expect(setPrimaryModuleConfig).toHaveBeenCalledWith({ model: undefined })
  })

  it('LoRA 第一行选择后写入 loras 数组（默认强度 0.8）', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByRole('button', { name: 'LoRA 1' })).toBeTruthy())
    chooseOption('LoRA 1', 'cunnyfunky_v5.0_000008.safetensors')
    expect(setPrimaryModuleConfig).toHaveBeenCalledWith({
      loras: [{
        name: 'cunnyfunky_v5.0_000008.safetensors',
        strength_model: 0.8,
        strength_clip: 0.8,
      }],
    })
  })

  it('已有一条 LoRA 时出现第二行与强度输入', async () => {
    renderPanel({
      loras: [{ name: 'cunnyfunky_v5.0_000008.safetensors', strength_model: 0.6, strength_clip: 0.6 }],
    })
    expect(await screen.findByRole('button', { name: 'LoRA 2' })).toBeTruthy()
    const strength = screen.getByRole('spinbutton', { name: 'LoRA 1 强度' }) as HTMLInputElement
    expect(strength.value).toBe('0.6')
    fireEvent.change(strength, { target: { value: '1.2' } })
    expect(setPrimaryModuleConfig).toHaveBeenCalledWith({
      loras: [{
        name: 'cunnyfunky_v5.0_000008.safetensors',
        strength_model: 1.2,
        strength_clip: 1.2,
      }],
    })
  })
})
