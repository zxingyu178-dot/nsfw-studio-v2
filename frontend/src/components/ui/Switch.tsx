import { useId, type InputHTMLAttributes } from 'react'

export interface SwitchProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: string
}

export function Switch({ label, className = '', id, checked, defaultChecked, ...rest }: SwitchProps) {
  const autoId = useId()
  const inputId = id ?? autoId
  return (
    <>
      <span className={`ds-switch ${className}`.trim()}>
        <input
          id={inputId}
          type="checkbox"
          role="switch"
          className="ds-switch__input"
          checked={checked}
          defaultChecked={defaultChecked}
          {...rest}
        />
        <span className="ds-switch__track" aria-hidden="true">
          <span className="ds-switch__thumb" />
        </span>
      </span>
      {label && (
        <label className="ds-switch__label" htmlFor={inputId}>
          {label}
        </label>
      )}
    </>
  )
}
