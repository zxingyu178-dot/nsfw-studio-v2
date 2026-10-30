import { describe, expect, it, beforeEach } from 'vitest'
import {
  availableImageModuleIds,
  getWorkbenchState,
  hydrateWorkbench,
  isImageCapablePrimary,
  isImageStartModule,
  isReleaseReady,
  releaseStatusNotice,
  resetWorkbench,
  setModuleCatalog,
  textPrimaryCandidates,
} from './workbenchStore'
import type { ModuleCapabilitiesDTO } from '../types/workbench'

function makeModule(overrides: Partial<ModuleCapabilitiesDTO> = {}): ModuleCapabilitiesDTO {
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
    ...overrides,
  }
}

const release = (ready: boolean, hardware: string, verified: boolean) => ({
  registered: true,
  binding_valid: true,
  dependencies_ready: true,
  real_gate_passed: ready,
  hardware_status: hardware,
  default_profile_verified: verified,
  ready_to_run: ready,
})

describe('W1 工作流放行状态', () => {
  it('未通过 G3 的模块即使 available 也不能进入正常选择列表', () => {
    const anime = makeModule({
      module_id: 'anime_generate',
      available: true,
      release_status: release(false, 'experimental', false),
    })
    expect(isReleaseReady(anime)).toBe(false)
    expect(textPrimaryCandidates([anime])).toEqual([])
  })

  it('旧后端没有 release_status 时回落到 available', () => {
    const legacy = makeModule({ module_id: 'legacy_generate' })
    expect(isReleaseReady(legacy)).toBe(true)
    expect(textPrimaryCandidates([legacy]).map((m) => m.module_id)).toEqual(['legacy_generate'])
  })

  it('已放行的慢速/未验证默认配置会显示提示但不隐藏', () => {
    const reference = makeModule({
      module_id: 'reference_generate',
      input_required: true,
      can_start_from_image: true,
      input_slots: [{ role: 'reference', required: true, max_count: 1 }],
      release_status: release(true, 'slow', false),
    })
    expect(isReleaseReady(reference)).toBe(true)
    expect(isImageStartModule(reference)).toBe(true)
    const notice = releaseStatusNotice(reference)
    expect(notice).toContain('较慢')
    expect(notice).toContain('G4')
  })

  it('图片起点模块同样执行放行门禁', () => {
    const blocked = makeModule({
      module_id: 'blocked_img',
      input_required: true,
      can_start_from_image: true,
      input_slots: [{ role: 'source', required: true, max_count: 1 }],
      release_status: release(false, 'experimental', false),
    })
    expect(isImageStartModule(blocked)).toBe(false)
    expect(releaseStatusNotice(blocked)).toBeNull()
  })
})

describe('W1.1 图片模块放行（availableImageModuleIds）', () => {
  beforeEach(() => {
    resetWorkbench()
  })

  const sourceModule = (ready: boolean, id = 'blocked_source') =>
    makeModule({
      module_id: id,
      input_required: true,
      can_start_from_image: true,
      input_slots: [{ role: 'source', required: true, max_count: 1 }],
      release_status: release(ready, ready ? 'slow' : 'experimental', ready),
    })

  const referenceModule = (ready: boolean, id = 'blocked_reference') =>
    makeModule({
      module_id: id,
      input_required: true,
      can_start_from_image: true,
      input_slots: [{ role: 'reference', required: true, max_count: 1 }],
      release_status: release(ready, ready ? 'slow' : 'experimental', ready),
    })

  it('source 槽模块未放行：available=true 也不能进入图片模块池', () => {
    expect(availableImageModuleIds([sourceModule(false)])).toEqual([])
  })

  it('reference 槽模块未放行：不能借能力识别绕过', () => {
    expect(availableImageModuleIds([referenceModule(false)])).toEqual([])
  })

  it('未登记 binding（ready=false + notes）被排除', () => {
    const unregistered = makeModule({
      module_id: 'unregistered',
      input_required: true,
      input_slots: [{ role: 'source', required: true, max_count: 1 }],
      release_status: {
        ...release(false, 'unverified', false),
        notes: '未在 release_manifest 登记',
      },
    })
    expect(availableImageModuleIds([unregistered])).toEqual([])
  })

  it('正常 img2img v2 与 reference v1 仍在图片模块池', () => {
    const img2img = sourceModule(true, 'img2img')
    const reference = referenceModule(true, 'reference_generate')
    expect(availableImageModuleIds([img2img, reference])).toEqual(['img2img', 'reference_generate'])
  })

  it('旧后端没有 release_status 时保持兼容', () => {
    const legacy = makeModule({
      module_id: 'legacy_img2img',
      input_required: true,
      can_start_from_image: true,
      input_slots: [{ role: 'source', required: true, max_count: 1 }],
    })
    expect(availableImageModuleIds([legacy])).toEqual(['legacy_img2img'])
  })

  it('Recipe 恢复未放行模块时，Primary 不可提交', () => {
    setModuleCatalog([sourceModule(false)])
    hydrateWorkbench({
      prompt_mode: 'structured',
      structured_prompt: {
        style: '', face: '', clothing: '', pose: '',
        scene: '', composition: '', lighting: '', extra: '',
      },
      full_prompt: '',
      negative_prompt: '',
      selected_assets: {},
      generation_mode: 'image',
      input_images: [{ role: 'source', image_id: 'img-1' }],
      width: 768,
      height: 768,
      count: 1,
      seed_mode: 'random',
      seed: null,
      workflow_modules: [{ module_id: 'blocked_source', binding_version: 'v1' }],
      source_prompt_id: null,
      source_prompt_version_id: null,
    })
    expect(getWorkbenchState().mode).toBe('image')
    expect(isImageCapablePrimary(getWorkbenchState())).toBe(false)
  })
})
