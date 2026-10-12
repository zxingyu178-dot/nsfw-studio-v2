import { describe, expect, it } from 'vitest'
import { isImageStartModule } from './workbenchStore'
import type { ModuleCapabilitiesDTO } from '../types/workbench'

/** 构造一个最小可用的模块能力对象，按需覆盖字段。 */
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
    ...overrides,
  }
}

describe('isImageStartModule（计划 §21：能力判断，不再靠 output_kind==="processed"）', () => {
  it('can_start_from_image=true 即判定为图片起点模块（即使 output_kind 不是 processed）', () => {
    const m = makeModule({ output_kind: 'something_else', can_start_from_image: true })
    expect(isImageStartModule(m)).toBe(true)
  })

  it('声明了 source/reference/face_reference slot 也算（即使无 can_start_from_image）', () => {
    expect(
      isImageStartModule(
        makeModule({ can_start_from_image: false, input_slots: [{ role: 'face_reference', required: true, max_count: 1 }] }),
      ),
    ).toBe(true)
    expect(
      isImageStartModule(
        makeModule({ can_start_from_image: false, input_slots: [{ role: 'reference', required: false, max_count: 2 }] }),
      ),
    ).toBe(true)
  })

  it('不可用 / 非输入必需 → 否', () => {
    expect(isImageStartModule(makeModule({ available: false }))).toBe(false)
    expect(isImageStartModule(makeModule({ input_required: false }))).toBe(false)
  })

  it('既无 can_start_from_image 也无图片 slot → 否', () => {
    expect(
      isImageStartModule(makeModule({ can_start_from_image: false, input_slots: [] })),
    ).toBe(false)
  })

  it('allowed_job_kinds 不含 process → 否；无该字段或含 process → 是', () => {
    const base = makeModule({ can_start_from_image: true })
    expect(isImageStartModule({ ...base, allowed_job_kinds: ['generate'] })).toBe(false)
    expect(isImageStartModule({ ...base, allowed_job_kinds: ['process'] })).toBe(true)
    expect(isImageStartModule({ ...base, allowed_job_kinds: ['generate', 'process'] })).toBe(true)
    expect(isImageStartModule({ ...base, allowed_job_kinds: [] })).toBe(true)
    expect(isImageStartModule({ ...base, allowed_job_kinds: undefined })).toBe(true)
  })
})
