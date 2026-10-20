/**
 * UI3 ChoiceTile —— 可视选择瓦片（以形状预览为主，而非纯文字）。
 *
 * 用于宽高比选择（1:1 / 3:4 / 9:16 / 16:9 等）：内部按比例画出对应形状。
 *
 * 2026-10-20 修复：此前用 CSS `aspect-ratio: "3:4"`（冒号格式非法）且内部盒子被
 * `.ui3-tile__shape-inner { width:100%; height:100% }` 强制成 28×28，导致所有画幅
 * 瓦片长得完全一样（用户反馈"选择尺寸的预览图都是一样的"）。现改为按比例计算像素
 * 尺寸，内联 width/height，保证 3:4 / 9:16 / 16:9 等一眼可分。
 */
import type { ReactNode } from 'react'

export type ChoiceShape = '1:1' | '3:4' | '4:3' | '9:16' | '16:9' | '2:3'

export interface ChoiceTileProps {
  /** 形状比例（决定内部预览框宽高比）。 */
  shape: ChoiceShape
  selected?: boolean
  onSelect?: () => void
  /** 下方小标签，可空。 */
  label?: ReactNode
  disabled?: boolean
  className?: string
  ariaLabel?: string
}

/** 预览框长边像素（与 CSS `.ui3-tile__shape` 高度一致）。 */
export const CHOICE_TILE_LONG_EDGE = 28

/** 把 "w:h" 形状换算成实际像素尺寸（长边固定，短边按比例）。 */
export function shapePixels(shape: ChoiceShape): { width: number; height: number } {
  const [w, h] = shape.split(':').map((part) => Number(part))
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) {
    return { width: CHOICE_TILE_LONG_EDGE, height: CHOICE_TILE_LONG_EDGE }
  }
  return w >= h
    ? {
        width: CHOICE_TILE_LONG_EDGE,
        height: Math.max(1, Math.round((CHOICE_TILE_LONG_EDGE * h) / w)),
      }
    : {
        width: Math.max(1, Math.round((CHOICE_TILE_LONG_EDGE * w) / h)),
        height: CHOICE_TILE_LONG_EDGE,
      }
}

export function ChoiceTile({
  shape,
  selected = false,
  onSelect,
  label,
  disabled,
  className = '',
  ariaLabel,
}: ChoiceTileProps) {
  const classes = [
    'ui3-tile',
    selected ? 'ui3-tile--selected' : '',
    disabled ? 'ui3-tile--disabled' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  const pixels = shapePixels(shape)

  return (
    <button
      type="button"
      className={classes}
      aria-pressed={selected}
      aria-label={ariaLabel ?? (typeof label === 'string' ? label : shape)}
      disabled={disabled}
      onClick={onSelect}
      data-shape={shape}
    >
      <span className="ui3-tile__shape" aria-hidden="true">
        <span
          className="ui3-tile__shape-inner"
          style={{ width: `${pixels.width}px`, height: `${pixels.height}px`, maxWidth: 'none', maxHeight: 'none' }}
        />
      </span>
      {label != null && label !== '' && <span className="ui3-tile__label">{label}</span>}
    </button>
  )
}
