/**
 * W1.2-A 验收：InspectorPanel 工作流下拉必须按模式显示正确的候选。
 * - 文生图：基础生成 + 动漫生成（无输入图的生成型模块）；
 * - 图片模式：img2img + reference_generate（声明图片输入槽的生成型模块）；
 * - 未放行：不出现在下拉，且只剩一个候选时退回静态标题。
 * 使用真实 workbenchStore 候选函数，只替换 useWorkbench 的状态。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ModuleCapabilitiesDTO } from '../../../types/workbench'

let mockState: Record<string, unknown>

vi.mock('../../../stores/workbenchStore', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../stores/workbenchStore')>()
  return {
    ...actual,
    useWorkbench: () => mockState,
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
  engineRuntimeApi: { preflight: vi.fn() },
}))

import { InspectorPanel } from './InspectorPanel'
import { engineRuntimeApi } from '../../../api/client'
import type { RuntimePreflightDTO } from '../../../types/workbench'

const release = {
  registered: true,
  binding_valid: true,
  dependencies_ready: true,
  real_gate_passed: true,
  hardware_status: 'normal',
  default_profile_verified: true,
  ready_to_run: true,
}

function makeModule(overrides: Partial<ModuleCapabilitiesDTO>): ModuleCapabilitiesDTO {
  return {
    module_id: 'm',
    module_version: 'v1',
    title: 'm',
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
    binding_version: 'v1',
    unavailable_reason: null,
    is_generative: true,
    allowed_job_kinds: ['generate'],
    release_status: release,
    parameters: [],
    input_slots: [],
    ...overrides,
  }
}

const basic = makeModule({ module_id: 'basic_generate', title: '基础生成', is_default: true })
const anime = makeModule({ module_id: 'anime_generate', title: '动漫生成' })
const img2img = makeModule({
  module_id: 'img2img',
  title: '图生图',
  input_required: true,
  input_kind: 'image',
  input_slots: [{ role: 'source', required: true, max_count: 1 }],
})
const reference = makeModule({
  module_id: 'reference_generate',
  title: '参考图生成',
  input_required: true,
  input_kind: 'image',
  input_slots: [{ role: 'reference', required: true, max_count: 1 }],
})
const upscale = makeModule({
  module_id: 'upscale',
  title: '高清放大',
  input_required: true,
  input_kind: 'image',
  allowed_job_kinds: ['generate', 'process'],
  is_generative: false,
  input_slots: [{ role: 'source', required: true, max_count: 1 }],
})
const unreleasedAnime = {
  ...anime,
  release_status: { ...release, real_gate_passed: false, ready_to_run: false },
}

function renderPanel(mode: 'text' | 'image', primary: string, catalog: ModuleCapabilitiesDTO[]) {
  mockState = {
    mode,
    moduleCatalog: catalog,
    workflowModules: [{ module_id: primary }],
    width: 768,
    height: 1024,
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

function optionLabels(): string[] {
  return screen.queryAllByRole('option').map((item) => item.textContent ?? '')
}

beforeEach(() => {
  mockState = {}
})

describe('W1.2-A InspectorPanel 工作流候选', () => {
  it('文生图：显示基础生成与动漫生成，不混入图片/处理模块', () => {
    renderPanel('text', 'basic_generate', [basic, anime, img2img, reference, upscale])
    fireEvent.click(screen.getByRole('button', { name: '工作流' }))
    expect(optionLabels()).toEqual(expect.arrayContaining(['基础生成', '动漫生成']))
    expect(optionLabels()).not.toContain('图生图')
    expect(optionLabels()).not.toContain('参考图生成')
    expect(optionLabels()).not.toContain('高清放大')
  })

  it('图片模式：显示 img2img 与 reference_generate，不混入文生图/upscale', () => {
    renderPanel('image', 'img2img', [basic, anime, img2img, reference, upscale])
    fireEvent.click(screen.getByRole('button', { name: '工作流' }))
    expect(optionLabels()).toEqual(expect.arrayContaining(['图生图', '参考图生成']))
    expect(optionLabels()).not.toContain('基础生成')
    expect(optionLabels()).not.toContain('动漫生成')
    expect(optionLabels()).not.toContain('高清放大')
  })

  it('未放行模块自动隐藏；唯一候选时退回静态标题', () => {
    renderPanel('text', 'basic_generate', [basic, unreleasedAnime])
    expect(screen.queryByRole('button', { name: '工作流' })).toBeNull()
    expect(screen.getByText('基础生成')).toBeTruthy()
  })

  it('默认工作流未放行：显示明确提示，且不自动选择其他工作流', () => {
    const unreleasedBasic = {
      ...basic,
      release_status: { ...release, real_gate_passed: false, ready_to_run: false },
    }
    renderPanel('text', '', [unreleasedBasic, anime])
    const alert = screen.getByRole('alert')
    expect(alert.textContent).toContain('默认工作流')
    expect(alert.textContent).toContain('不可用')
    // 用户仍可显式选择已放行的 anime（但系统不会自动替选）
    fireEvent.click(screen.getByRole('button', { name: '工作流' }))
    expect(optionLabels()).toContain('动漫生成')
  })
})

function preflightResult(
  status: RuntimePreflightDTO['status'],
  overrides: Partial<RuntimePreflightDTO['modules'][number]> = {},
): RuntimePreflightDTO {
  return {
    status,
    engine: { online: status !== 'UNKNOWN', version: '0.37.0' },
    modules: [{
      module_id: 'basic_generate',
      binding_version: 'v1',
      workflow_hash: 'wf',
      binding_hash: 'bh',
      status,
      missing_nodes: [],
      missing_models: [],
      missing_requirements: [],
      unknown_reasons: [],
      notes: [],
      cache_hit: false,
      ...overrides,
    }],
    checked_at: '2026-10-31T00:00:00Z',
    cache_hit: false,
  }
}

describe('W2.0 Runtime Preflight UI', () => {
  it('READY：点击检测后显示可运行状态', async () => {
    vi.mocked(engineRuntimeApi.preflight).mockResolvedValue(preflightResult('READY'))
    renderPanel('text', 'basic_generate', [basic, anime])
    fireEvent.click(screen.getByRole('button', { name: '检查运行环境' }))
    const status = await screen.findByTestId('runtime-preflight-status')
    expect(status.textContent).toContain('READY')
    expect(engineRuntimeApi.preflight).toHaveBeenCalledWith(['basic_generate'])
  })

  it('BLOCKED：显示缺失节点/模型明细', async () => {
    vi.mocked(engineRuntimeApi.preflight).mockResolvedValue(preflightResult('BLOCKED', {
      missing_nodes: ['KSampler'],
      missing_models: [{ folder: 'loras', filename: 'missing.safetensors' }],
    }))
    renderPanel('text', 'basic_generate', [basic, anime])
    fireEvent.click(screen.getByRole('button', { name: '检查运行环境' }))
    const status = await screen.findByTestId('runtime-preflight-status')
    expect(status.textContent).toContain('BLOCKED')
    const details = screen.getByTestId('runtime-preflight-details')
    expect(details.textContent).toContain('KSampler')
    expect(details.textContent).toContain('loras/missing.safetensors')
  })

  it('UNKNOWN：显示离线/无法验证原因', async () => {
    vi.mocked(engineRuntimeApi.preflight).mockResolvedValue({
      ...preflightResult('UNKNOWN', { unknown_reasons: ['engine_offline'] }),
      engine: { online: false, version: '', detail: 'ComfyUI 不可达' },
    })
    renderPanel('text', 'basic_generate', [basic, anime])
    fireEvent.click(screen.getByRole('button', { name: '检查运行环境' }))
    const status = await screen.findByTestId('runtime-preflight-status')
    expect(status.textContent).toContain('UNKNOWN')
    const details = screen.getByTestId('runtime-preflight-details')
    expect(details.textContent).toContain('engine_offline')
  })
})
