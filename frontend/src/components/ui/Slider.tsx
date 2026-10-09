import type { CSSProperties, ReactNode } from 'react'

export interface SliderProps {
  min: number
  max: number
  step?: number
  value: number
  onChange: (value: number) => void
  id?: string
  disabled?: boolean
  /** 可选：右侧自定义值显示（通常传数字 Input 实现双向） */
  valueSlot?: ReactNode
  ariaLabel?: string
}

export function Slider({ min, max, step = 1, value, onChange, id, disabled, valueSlot, ariaLabel }: SliderProps) {
  const pct = max > min ? ((value - min) / (max - min)) * 100 : 0
  return (
    <div className={`ds-slider ${disabled ? 'ds-slider--disabled' : ''}`.trim()}>
      <input
        id={id}
        type="range"
        className="ds-slider__range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        aria-label={ariaLabel}
        style={{ '--ds-slider-pct': `${pct}%` } as CSSProperties}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      {valueSlot && <span className="ds-slider__value">{valueSlot}</span>}
    </div>
  )
}
