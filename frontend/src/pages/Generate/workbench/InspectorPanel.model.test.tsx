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
  // 只保留本文件需要的布尔开关；其余参数控件由组件自身测试覆盖。
  ModuleParameterField: ({ param, value, onChange }: {
    param: { name: string; type: string; title?: string; default?: unknown }
    value: unknown
    onChange: (value: unknown) => void
  }) =>
    param.type === 'bool' ? (
      <input
        type="checkbox"
        aria-label={param.title || param.name}
        checked={Boolean(value ?? param.default)}
        onChange={(event) => onChange(event.target.checked)}
      />
    ) : null,
}))
vi.mock('./SplitGenerateAction', () => ({
  SplitGenerateAction: () => <div data-testid="split-action" />,
}))
vi.mock('../../../api/client', () => ({
  engineRuntimeApi: {
    preflight: vi.fn(),
    models: vi.fn().mockResolvedValue({
      checkpoints: ['NoobAI-XL-v1.1.safetensors'],
      loras: ['cunnyfunky_v5.0_000008.safetensors', 'cunnyfunky_noobai_v3.3_000080.safetensors'],
      model_catalog: {
        'NoobAI-XL-v1.1.safetensors': {
          model_id: 'noobai_xl_v1_1',
          display_name: 'NoobAI XL v1.1 (eps)',
          family: 'sdxl_anime',
        },
      },
      lora_catalog: {
        'cunnyfunky_v5.0_000008.safetensors': {
          model_id: 'cunnyfunky_style',
          display_name: 'CunnyFunky Style v5',
          family: 'sdxl_anime',
          compatible_workflows: ['anime_generate'],
          base_models: ['NoobAI-XL-v1.1.safetensors'],
          recommended_strength: 0.6,
        },
      },
      sampling_profiles: {
        'NoobAI-XL-v1.1.safetensors': {
          steps: 30, cfg: 5.0, sampler_name: 'dpmpp_2m', scheduler: 'karras', denoise: 1.0,
        },
      },
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
  registry: { default_parameters: { model: 'NoobAI-XL-v1.1.safetensors' } },
  input_slots: [],
  is_default: true,
  parameters: [
    { name: 'model', type: 'string', required: false, default: '', title: '底模', configurable: true },
    { name: 'loras', type: 'lora_list', required: false, default: [], title: 'LoRA 叠加', configurable: false },
    { name: 'face_detailer', type: 'bool', required: false, default: true, title: '人脸修复（FaceDetailer）', configurable: true },
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
  fireEvent.click(screen.getByRole('option', { name: (name) => name.includes(optionText) }))
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
    expect(modelButton.textContent).toContain('NoobAI XL v1.1 (eps)')
    chooseOption('底模', '绑定默认')
    expect(setPrimaryModuleConfig).toHaveBeenCalledWith({ model: undefined })
  })

  it('LoRA 第一行选择后写入注册中心推荐强度', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByRole('button', { name: 'LoRA 1' })).toBeTruthy())
    chooseOption('LoRA 1', 'cunnyfunky_v5.0_000008.safetensors')
    expect(setPrimaryModuleConfig).toHaveBeenCalledWith({
      loras: [{
        name: 'cunnyfunky_v5.0_000008.safetensors',
        strength_model: 0.6,
        strength_clip: 0.6,
      }],
    })
  })

  it('未登记推荐强度的 LoRA 使用默认强度 0.8', async () => {
    renderPanel()
    await waitFor(() => expect(screen.getByRole('button', { name: 'LoRA 1' })).toBeTruthy())
    chooseOption('LoRA 1', 'cunnyfunky_noobai_v3.3_000080.safetensors')
    expect(setPrimaryModuleConfig).toHaveBeenCalledWith({
      loras: [{
        name: 'cunnyfunky_noobai_v3.3_000080.safetensors',
        strength_model: 0.8,
        strength_clip: 0.8,
      }],
    })
  })

  it('LoRA 下拉显示注册中心友好名称并保留文件名说明', async () => {
    renderPanel({
      loras: [{ name: 'cunnyfunky_v5.0_000008.safetensors', strength_model: 0.8, strength_clip: 0.8 }],
    })
    const trigger = await screen.findByRole('button', { name: 'LoRA 1' })
    expect(trigger.textContent).toContain('CunnyFunky Style v5')
    fireEvent.click(trigger)
    const option = screen.getAllByRole('option')
      .find((item) => item.textContent?.includes('cunnyfunky_v5.0_000008.safetensors'))
    expect(option?.textContent).toContain('CunnyFunky Style v5')
    expect(option?.textContent).toContain('cunnyfunky_v5.0_000008.safetensors')
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

  it('底模下拉为已登记推荐参数的模型显示“推荐”标记与文件名说明', async () => {
    renderPanel()
    fireEvent.click(await screen.findByRole('button', { name: '底模' }))
    const options = screen.getAllByRole('option')
    const noobai = options.find((option) => option.textContent?.includes('NoobAI-XL-v1.1.safetensors'))
    expect(noobai?.textContent).toContain('NoobAI XL v1.1 (eps)')
    expect(noobai?.textContent).toContain('推荐')
    const defaultOption = options.find((option) => option.textContent?.includes('绑定默认'))
    expect(defaultOption?.textContent).toContain('推荐')
    expect(defaultOption?.textContent).toContain('默认底模：NoobAI XL v1.1 (eps)')
  })

  it('选择登记的底模时显示推荐采样参数并可一键应用', async () => {
    renderPanel({ model: 'NoobAI-XL-v1.1.safetensors' })
    expect(await screen.findByText('推荐：30 步 · cfg5 · dpmpp_2m · karras')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '应用推荐' }))
    expect(setPrimaryModuleConfig).toHaveBeenCalledWith({
      steps: 30, cfg: 5.0, sampler_name: 'dpmpp_2m', scheduler: 'karras', denoise: 1.0,
    })
  })

  it('未显式选底模时显示默认底模的推荐参数并可应用', async () => {
    renderPanel()
    expect(await screen.findByText('默认底模推荐：30 步 · cfg5 · dpmpp_2m · karras')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '应用推荐' }))
    expect(setPrimaryModuleConfig).toHaveBeenCalledWith({
      steps: 30, cfg: 5.0, sampler_name: 'dpmpp_2m', scheduler: 'karras', denoise: 1.0,
    })
  })

  it('推荐参数已全部生效时显示“已采用推荐”，不再重复提供应用按钮', async () => {
    renderPanel({
      model: 'NoobAI-XL-v1.1.safetensors',
      steps: 30,
      cfg: 5.0,
      sampler_name: 'dpmpp_2m',
      scheduler: 'karras',
      denoise: 1.0,
    })
    expect(await screen.findByText('已采用推荐')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '应用推荐' })).toBeNull()
  })

  it('任一采样参数偏离推荐时重新显示应用按钮', async () => {
    renderPanel({
      model: 'NoobAI-XL-v1.1.safetensors',
      steps: 30,
      cfg: 4.5,
      sampler_name: 'dpmpp_2m',
      scheduler: 'karras',
      denoise: 1.0,
    })
    expect(await screen.findByRole('button', { name: '应用推荐' })).toBeTruthy()
    expect(screen.queryByText('已采用推荐')).toBeNull()
  })

  it('人脸修复默认开启，取消后写入 face_detailer=false', async () => {
    renderPanel()
    const checkbox = (await screen.findByRole('checkbox', {
      name: '人脸修复（FaceDetailer）',
    })) as HTMLInputElement
    expect(checkbox.checked).toBe(true)
    fireEvent.click(checkbox)
    expect(setPrimaryModuleConfig).toHaveBeenCalledWith({ face_detailer: false })
  })
})
