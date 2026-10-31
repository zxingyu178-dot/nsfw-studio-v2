import { describe, expect, it, beforeEach } from 'vitest'
import {
  availableImageModuleIds,
  getWorkbenchState,
  hydrateWorkbench,
  requiredInputSlot,
  resetWorkbench,
  setInputImage,
  setModuleCatalog,
  setPrimaryModule,
} from './workbenchStore'
import type { ModuleCapabilitiesDTO, WorkbenchSnapshot } from '../types/workbench'

function makeModule(overrides: Partial<ModuleCapabilitiesDTO> = {}): ModuleCapabilitiesDTO {
  return {
    module_id: 'm',
    module_version: '1',
    title: 'm',
    description: '',
    uses_seed: true,
    input_kind: 'image',
    input_required: true,
    input_role: 'source',
    output_kind: 'processed',
    parent_policy: 'independent',
    output_cardinality: 1,
    registered: true,
    available: true,
    provider: null,
    binding_version: null,
    unavailable_reason: null,
    is_generative: true,
    allowed_job_kinds: ['generate'],
    ...overrides,
  }
}

const img2img = makeModule({
  module_id: 'img2img',
  title: '图生图',
  can_start_from_image: true,
  input_slots: [{ role: 'source', required: true, max_count: 1, description: '以源图为基础重绘' }],
})
const referenceGenerate = makeModule({
  module_id: 'reference_generate',
  title: '参考图生成',
  can_start_from_image: true,
  allowed_job_kinds: ['generate'],
  input_slots: [{ role: 'reference', required: true, max_count: 1, description: '以参考图为构图/形象依据生成新图' }],
})
const basicGenerate = makeModule({
  module_id: 'basic_generate',
  title: '基础文生图',
  input_required: false,
  can_start_from_image: false,
  input_slots: [],
})
describe('requiredInputSlot（Phase 0.12 任务 11：role 从 input_slots 读取）', () => {
  it('img2img → source；reference_generate → reference；文生图无 slot → null', () => {
    expect(requiredInputSlot(img2img)).toMatchObject({ role: 'source', required: true, max_count: 1 })
    expect(requiredInputSlot(referenceGenerate)).toMatchObject({ role: 'reference' })
    expect(requiredInputSlot(null)).toBeNull()
    expect(requiredInputSlot(basicGenerate)).toBeNull()
  })
})

describe('availableImageModuleIds（纳入 reference_generate）', () => {
  it('reference_generate 虽 allowed_job_kinds 仅 generate，仍可作为图片生成 Primary', () => {
    const ids = availableImageModuleIds([img2img, referenceGenerate, basicGenerate])
    expect(ids).toContain('img2img')
    expect(ids).toContain('reference_generate')
  })
})

describe('切 Primary Module 时单图自动重映射 role', () => {
  beforeEach(() => {
    resetWorkbench()
    setModuleCatalog([img2img, referenceGenerate])
  })

  it('img2img→source，切到 reference_generate→reference，再切回 source', () => {
    setInputImage('img-A')
    expect(getWorkbenchState().inputImages[0].role).toBe('source')

    setPrimaryModule('reference_generate')
    expect(getWorkbenchState().workflowModules[0].module_id).toBe('reference_generate')
    expect(getWorkbenchState().inputImages[0].role).toBe('reference')
    // 图片未被静默丢弃
    expect(getWorkbenchState().inputImages[0].image_id).toBe('img-A')

    setPrimaryModule('img2img')
    expect(getWorkbenchState().inputImages[0].role).toBe('source')
  })

  it('Image→Workbench（setInputImage）role 跟随归一化后的 Primary', () => {
    resetWorkbench()
    setModuleCatalog([referenceGenerate, img2img])
    // 直接在 reference Primary 下选择输入图
    setPrimaryModule('reference_generate')
    setInputImage('img-B')
    expect(getWorkbenchState().inputImages[0].role).toBe('reference')
  })
})

describe('Recipe / History restore 保留 reference role 与 Primary', () => {
  beforeEach(() => {
    resetWorkbench()
    setModuleCatalog([img2img, referenceGenerate])
  })

  it('Recipe restore：input_images role=reference 与 reference_generate Primary 原样保留', () => {
    const snapshot = {
      prompt_mode: 'structured',
      structured_prompt: {},
      generation_mode: 'image',
      input_images: [{ role: 'reference', image_id: 'img-C' }],
      workflow_modules: [{ module_id: 'reference_generate' }],
    } as unknown as WorkbenchSnapshot
    hydrateWorkbench(snapshot)
    expect(getWorkbenchState().workflowModules[0].module_id).toBe('reference_generate')
    expect(getWorkbenchState().inputImages[0]).toMatchObject({ role: 'reference', image_id: 'img-C' })
  })

  it('History restore：恢复出的 source→img2img 与 reference→reference_generate 不被静默替换', () => {
    const recipeSnapshot = {
      prompt_mode: 'structured',
      structured_prompt: {},
      generation_mode: 'image',
      input_images: [{ role: 'source', image_id: 'img-D' }],
      workflow_modules: [{ module_id: 'img2img' }],
    } as unknown as WorkbenchSnapshot
    hydrateWorkbench(recipeSnapshot)
    expect(getWorkbenchState().workflowModules[0].module_id).toBe('img2img')
    expect(getWorkbenchState().inputImages[0].role).toBe('source')

    const historySnapshot = {
      prompt_mode: 'structured',
      structured_prompt: {},
      generation_mode: 'image',
      input_images: [{ role: 'reference', image_id: 'img-E' }],
      workflow_modules: [{ module_id: 'reference_generate' }],
    } as unknown as WorkbenchSnapshot
    hydrateWorkbench(historySnapshot)
    expect(getWorkbenchState().workflowModules[0].module_id).toBe('reference_generate')
    expect(getWorkbenchState().inputImages[0].role).toBe('reference')
  })
})
