import { describe, expect, it } from 'vitest'
import {
  isImageStartModule,
  isReleaseReady,
  releaseStatusNotice,
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
