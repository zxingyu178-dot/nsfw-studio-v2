import type { ReactNode } from 'react'

export interface RadioOption<T extends string> {
  value: T
  label: ReactNode
  disabled?: boolean
  ariaLabel?: string
}

/* ===== RadioGroup：垂直 / 横向单选项 ===== */
export interface RadioGroupProps<T extends string> {
  name: string
  options: RadioOption<T>[]
  value: T
  onChange: (value: T) => void
  direction?: 'row' | 'column'
  size?: 'sm' | 'md'
}

export function RadioGroup<T extends string>({
  name,
  options,
  value,
  onChange,
  direction = 'row',
  size = 'md',
}: RadioGroupProps<T>) {
  return (
    <div role="radiogroup" className={`ds-radio-group ds-radio-group--${direction}`}>
      {options.map((o) => {
        const active = o.value === value
        return (
          <label
            key={o.value}
            className={`ds-radio ds-radio--${size} ${active ? 'ds-radio--active' : ''} ${
              o.disabled ? 'ds-radio--disabled' : ''
            }`.trim()}
          >
            <input
              type="radio"
              name={name}
              className="ds-radio__input"
              value={o.value}
              checked={active}
              disabled={o.disabled}
              aria-label={o.ariaLabel}
              onChange={() => onChange(o.value)}
            />
            <span className="ds-radio__circle" aria-hidden="true" />
            <span className="ds-radio__text">{o.label}</span>
          </label>
        )
      })}
    </div>
  )
}

/* ===== SegmentedControl：紧凑分段切换 ===== */
export interface SegmentedProps<T extends string> {
  options: RadioOption<T>[]
  value: T
  onChange: (value: T) => void
  block?: boolean
  size?: 'sm' | 'md'
  ariaLabel?: string
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  block,
  size = 'md',
  ariaLabel,
}: SegmentedProps<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className={`ds-segmented ds-segmented--${size} ${block ? 'ds-segmented--block' : ''}`.trim()}
    >
      {options.map((o) => {
        const active = o.value === value
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={o.disabled}
            className={`ds-segmented__item ${active ? 'ds-segmented__item--active' : ''}`.trim()}
            onClick={() => onChange(o.value)}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
