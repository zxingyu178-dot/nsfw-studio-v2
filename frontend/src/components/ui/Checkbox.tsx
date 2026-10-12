import { useId, type InputHTMLAttributes, type ReactNode } from 'react'

export interface CheckboxProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: ReactNode
}

export function Checkbox({ label, className = '', id, ...rest }: CheckboxProps) {
  const autoId = useId()
  const inputId = id ?? autoId
  return (
    <span className={`ds-check ${className}`.trim()}>
      <input id={inputId} type="checkbox" className="ds-check__input" {...rest} />
      {label && (
        <label className="ds-check__label" htmlFor={inputId}>
          {label}
        </label>
      )}
    </span>
  )
}
