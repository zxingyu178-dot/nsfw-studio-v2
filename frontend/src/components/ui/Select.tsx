import type { SelectHTMLAttributes } from 'react'
import { IconChevronDown } from './icons'

export interface SelectOption {
  value: string | number
  label: string
  disabled?: boolean
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  options: SelectOption[]
  placeholder?: string
  invalid?: boolean
}

export function Select({ options, placeholder, invalid, className = '', id, ...rest }: SelectProps) {
  return (
    <div className={`ds-select ${invalid ? 'ds-input--invalid' : ''}`.trim()}>
      <select id={id} className={`ds-select__native ${className}`.trim()} {...rest}>
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((o) => (
          <option key={String(o.value)} value={o.value} disabled={o.disabled}>
            {o.label}
          </option>
        ))}
      </select>
      <span className="ds-select__arrow" aria-hidden="true">
        <IconChevronDown size={14} />
      </span>
    </div>
  )
}
