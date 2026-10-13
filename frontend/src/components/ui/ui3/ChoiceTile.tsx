/**
 * UI3 ChoiceTile —— 可视选择瓦片（以形状预览为主，而非纯文字）。
 *
 * 用于宽高比选择（1:1 / 3:4 / 9:16 / 16:9 等）：内部用 CSS aspect-ratio
 * 画出对应形状。可选文字标签（如 "3:4"）。
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

  return (
    <button
      type="button"
      className={classes}
      aria-pressed={selected}
      aria-label={ariaLabel ?? (typeof label === 'string' ? label : shape)}
      disabled={disabled}
      onClick={onSelect}
    >
      <span className="ui3-tile__shape" style={{ aspectRatio: shape }} aria-hidden="true">
        <span className="ui3-tile__shape-inner" />
      </span>
      {label != null && label !== '' && <span className="ui3-tile__label">{label}</span>}
    </button>
  )
}
