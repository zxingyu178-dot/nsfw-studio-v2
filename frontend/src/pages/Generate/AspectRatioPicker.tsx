import { useState } from 'react'
import { Field, Input, Select } from '../../components/ui'
import {
  ASPECT_RATIOS,
  clampDimension,
  computeDimensions,
  inferAspect,
  isSlowSize,
  type AspectKey,
  type ResolutionTier,
} from '../../utils/aspectRatio'

interface AspectRatioPickerProps {
  /** 当前已提交宽高（来自 store）。 */
  width: number
  height: number
  /** 宽高变化（含预设计算与自定义手填）→ 写回 store。 */
  onSizeChange: (width: number, height: number) => void
}

/**
 * 画幅 + 分辨率预设选择器（Commit 6）。
 * 纯前端便捷选择：选画幅/档位即计算宽高并写回；选“自定义”则手填宽高。
 * 总像素超阈值时仅提示“生成较慢”，不阻断生成。
 */
export function AspectRatioPicker({ width, height, onSizeChange }: AspectRatioPickerProps) {
  // 从已提交宽高尽量回选画幅（快照 hydrate 后避免显示错误）；无法匹配则自定义。
  const [aspect, setAspect] = useState<AspectKey>(() => inferAspect(width, height))
  const [tier, setTier] = useState<ResolutionTier>('standard')
  const [widthText, setWidthText] = useState(String(width))
  const [heightText, setHeightText] = useState(String(height))

  function handleAspectChange(key: AspectKey): void {
    setAspect(key)
    if (key === 'custom') {
      // 切到自定义：以当前 store 宽高初始化输入框
      setWidthText(String(width))
      setHeightText(String(height))
      return
    }
    const dims = computeDimensions(key, tier)
    onSizeChange(dims.width, dims.height)
  }

  function handleTierChange(next: ResolutionTier): void {
    setTier(next)
    if (aspect !== 'custom') {
      const dims = computeDimensions(aspect, next)
      onSizeChange(dims.width, dims.height)
    }
  }

  function commitCustomSize(): void {
    const nextWidth = clampDimension(Number.parseInt(widthText, 10))
    const nextHeight = clampDimension(Number.parseInt(heightText, 10))
    setWidthText(String(nextWidth))
    setHeightText(String(nextHeight))
    onSizeChange(nextWidth, nextHeight)
  }

  return (
    <div className="size-row size-row--preset">
      <Field label="画幅">
        <Select
          aria-label="画幅"
          value={aspect}
          onChange={(event) => handleAspectChange(event.target.value as AspectKey)}
          options={[
            ...ASPECT_RATIOS.map((ratio) => ({ value: ratio.key, label: ratio.label })),
            { value: 'custom', label: '自定义' },
          ]}
        />
      </Field>
      <Field label="分辨率">
        <Select
          aria-label="分辨率档位"
          value={tier}
          onChange={(event) => handleTierChange(event.target.value as ResolutionTier)}
          options={[
            { value: 'standard', label: '标准（长边 1024）' },
            { value: 'hd', label: '高清（长边 1920）' },
          ]}
        />
      </Field>

      {aspect === 'custom' && (
        <>
          <Field label="宽度 (px)">
            <Input
              type="number" min={64} max={4096} step={8} aria-label="宽度"
              value={widthText}
              onChange={(event) => setWidthText(event.target.value)}
              onBlur={commitCustomSize}
            />
          </Field>
          <Field label="高度 (px)">
            <Input
              type="number" min={64} max={4096} step={8} aria-label="高度"
              value={heightText}
              onChange={(event) => setHeightText(event.target.value)}
              onBlur={commitCustomSize}
            />
          </Field>
        </>
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
