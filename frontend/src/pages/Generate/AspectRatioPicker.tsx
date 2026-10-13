import { useState } from 'react'
import { ChoiceGrid, ChoiceTile, NumberStepper, type ChoiceShape } from '../../components/ui/ui3'
import {
  ASPECT_RATIOS,
  computeDimensions,
  inferAspect,
  isSlowSize,
  type AspectKey,
  type PresetAspectKey,
  type ResolutionTier,
} from '../../utils/aspectRatio'

interface AspectRatioPickerProps {
  /** 当前已提交宽高（来自 store）。 */
  width: number
  height: number
  /** 宽高变化（含预设计算与自定义手填）→ 写回 store。 */
  onSizeChange: (width: number, height: number) => void
}

/** Resolution tier + 自定义。 */
type Tier = ResolutionTier | 'custom'

/**
 * 画幅 + 分辨率（UI 3.0）：
 * - 画幅用形状 ChoiceTile（直接看比例形状，不用原生 select）；
 * - 分辨率用 segmented ChoiceGrid（标准 / 高清 / 自定义）；
 * - 自定义宽高用 NumberStepper（钳制 64~4096）。
 * 业务不变：Job 仍只提交 width/height；画幅/档位只是便捷选择，不入快照。
 */
const TILE_SHAPE: Record<PresetAspectKey, ChoiceShape> = {
  '1:1': '1:1',
  '3:4': '3:4',
  '4:5': '3:4',
  '9:16': '9:16',
  '16:9': '16:9',
  '5:4': '4:3',
  '4:3': '4:3',
}

const CUSTOM_MIN = 64
const CUSTOM_MAX = 4096

export function AspectRatioPicker({ width, height, onSizeChange }: AspectRatioPickerProps) {
  const initial: AspectKey = inferAspect(width, height)
  const [ratio, setRatio] = useState<PresetAspectKey>(initial === 'custom' ? '1:1' : initial)
  const [tier, setTier] = useState<Tier>(initial === 'custom' ? 'custom' : 'standard')
  // 自定义宽高用组件内部状态（与旧实现一致：互不依赖 store 回灌）。
  const [customW, setCustomW] = useState(width)
  const [customH, setCustomH] = useState(height)

  function handleRatioSelect(key: PresetAspectKey): void {
    setRatio(key)
    if (tier !== 'custom') {
      const dims = computeDimensions(key, tier)
      onSizeChange(dims.width, dims.height)
    }
  }

  function handleTierSelect(next: Tier): void {
    setTier(next)
    if (next !== 'custom') {
      const dims = computeDimensions(ratio, next)
      onSizeChange(dims.width, dims.height)
    }
  }

  function handleCustomWidth(w: number): void {
    setCustomW(w)
    onSizeChange(w, customH)
  }

  function handleCustomHeight(h: number): void {
    setCustomH(h)
    onSizeChange(customW, h)
  }

  return (
    <div className="wb-param">
      <ChoiceGrid columns={4} label="画幅">
        {ASPECT_RATIOS.map((ratioDef) => (
          <ChoiceTile
            key={ratioDef.key}
            shape={TILE_SHAPE[ratioDef.key]}
            selected={ratio === ratioDef.key && tier !== 'custom'}
            onSelect={() => handleRatioSelect(ratioDef.key)}
            label={ratioDef.key}
            ariaLabel={ratioDef.key}
          />
        ))}
      </ChoiceGrid>

      <ChoiceGrid columns={3} label="分辨率">
        <ChoiceTile
          shape="1:1"
          selected={tier === 'standard'}
          onSelect={() => handleTierSelect('standard')}
          label="标准"
          ariaLabel="标准"
        />
        <ChoiceTile
          shape="1:1"
          selected={tier === 'hd'}
          onSelect={() => handleTierSelect('hd')}
          label="高清"
          ariaLabel="高清"
        />
        <ChoiceTile
          shape="1:1"
          selected={tier === 'custom'}
          onSelect={() => handleTierSelect('custom')}
          label="自定义"
          ariaLabel="自定义"
        />
      </ChoiceGrid>

      {tier === 'custom' && (
        <div className="wb-seed-row">
          <NumberStepper
            value={customW}
            min={CUSTOM_MIN}
            max={CUSTOM_MAX}
            step={8}
            ariaLabel="宽度"
            onChange={handleCustomWidth}
          />
          <NumberStepper
            value={customH}
            min={CUSTOM_MIN}
            max={CUSTOM_MAX}
            step={8}
            ariaLabel="高度"
            onChange={handleCustomHeight}
          />
        </div>
      )}

      <p className="wb-static muted" data-testid="size-current">
        当前 {width} × {height}
      </p>

      {isSlowSize(width, height) && (
        <p className="ds-notice ds-notice--warning" role="status">
          该尺寸生成较慢，属正常现象
        </p>
      )}
    </div>
  )
}

export default AspectRatioPicker
