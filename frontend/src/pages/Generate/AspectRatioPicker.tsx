import { useEffect, useRef, useState } from 'react'
import { ChoiceGrid, ChoiceTile, NumberStepper, type ChoiceShape } from '../../components/ui/ui3'
import {
  ASPECT_RATIOS,
  computeDimensions,
  deriveTier,
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
  const [tier, setTier] = useState<Tier>(
    initial === 'custom' ? 'custom' : deriveTier(width, height),
  )
  // 自定义宽高用组件内部状态（与旧实现一致：互不依赖 store 回灌）。
  const [customW, setCustomW] = useState(width)
  const [customH, setCustomH] = useState(height)
  // 用户聚焦在自定义输入期间，外部 hydrate / store 回灌不逐字符打断；失焦后再对齐。
  const customEditingRef = useRef(false)
  // 编辑期间被跳过的外部同步标记：失焦时若存在 pending，才用最新外部值对齐。
  const syncPendingRef = useRef(false)

  // 外部 width/height 变化（Recipe hydrate / History restore / 图片→Workbench）后，
  // 回选对应画幅与档位。守卫：派生目标与当前状态一致时不 set，从根上避免 effect 循环；
  // 自定义输入正被聚焦编辑时整体跳过回灌（避免输入中途匹配预设时 tier 被切走、输入框卸载），
  // 失焦后由 handleCustomBlur 统一对齐。
  function syncFromExternal(w: number, h: number): void {
    const derived: AspectKey = inferAspect(w, h)
    setTier((prev) => {
      const nextTier: Tier = derived === 'custom' ? 'custom' : deriveTier(w, h)
      return prev === nextTier ? prev : nextTier
    })
    if (derived !== 'custom') {
      setRatio((prev) => (prev === derived ? prev : derived))
    }
    setCustomW((prev) => (prev === w ? prev : w))
    setCustomH((prev) => (prev === h ? prev : h))
  }

  useEffect(() => {
    if (customEditingRef.current) {
      // 编辑中：整体跳过回灌，并标记失焦后需要对齐（外部 hydrate 可能已改写 store）。
      syncPendingRef.current = true
      return
    }
    syncFromExternal(width, height)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [width, height])

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

  function handleCustomFocus(): void {
    customEditingRef.current = true
  }

  function handleCustomBlur(): void {
    customEditingRef.current = false
    // 仅当编辑期间确有外部 hydrate 被跳过，才在失焦后对齐；普通提交路径 props 未变，不回灌。
    if (syncPendingRef.current) {
      syncPendingRef.current = false
      syncFromExternal(width, height)
    }
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
            onFocus={handleCustomFocus}
            onBlur={handleCustomBlur}
          />
          <NumberStepper
            value={customH}
            min={CUSTOM_MIN}
            max={CUSTOM_MAX}
            step={8}
            ariaLabel="高度"
            onChange={handleCustomHeight}
            onFocus={handleCustomFocus}
            onBlur={handleCustomBlur}
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
