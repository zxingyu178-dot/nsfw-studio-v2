import { describe, expect, it } from 'vitest'
import { ratioLabel } from './GalleryCard'

describe('图库卡片比例标签（Phase 0.18 C）', () => {
  it('常见比例化简为「w:h」', () => {
    expect(ratioLabel(1024, 1024)).toBe('1:1')
    expect(ratioLabel(1152, 1536)).toBe('3:4')
    expect(ratioLabel(1024, 576)).toBe('16:9')
  })

  it('化简后边长超过 16 的非标准比例回退到「W×H」', () => {
    expect(ratioLabel(832, 1216)).toBe('832×1216')
    expect(ratioLabel(1000, 999)).toBe('1000×999')
  })

  it('缺省尺寸返回空串', () => {
    expect(ratioLabel(0, 0)).toBe('')
  })
})
