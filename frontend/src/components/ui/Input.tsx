import type {
  InputHTMLAttributes,
  ReactNode,
  TextareaHTMLAttributes,
} from 'react'

/* ===== Field：标签 + 控件 + 错误 / 提示 ===== */
interface FieldProps {
  label?: ReactNode
  htmlFor?: string
  error?: ReactNode
  hint?: ReactNode
  required?: boolean
  children: ReactNode
  className?: string
  actions?: ReactNode
}

export function Field({ label, htmlFor, error, hint, required, children, className = '', actions }: FieldProps) {
  return (
    <div className={`ds-field ${error ? 'ds-field--invalid' : ''} ${className}`.trim()}>
      {(label || actions) && (
        <div className="ds-field__label-row">
          {label && (
            <label className="ds-field__label" htmlFor={htmlFor}>
              {label}
              {required && <span className="ds-field__required" aria-hidden="true"> *</span>}
            </label>
          )}
          {actions && <div className="ds-field__actions">{actions}</div>}
        </div>
      )}
      {children}
      {error ? (
        <p className="ds-field__error" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="ds-field__hint">{hint}</p>
      ) : null}
    </div>
  )
}

/* ===== Input ===== */
export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'prefix'> {
  invalid?: boolean
  prefix?: ReactNode
  suffix?: ReactNode
}

export function Input({ invalid, prefix, suffix, className = '', id, ...rest }: InputProps) {
  if (prefix || suffix) {
    return (
      <div
        className={`ds-input-group ${invalid ? 'ds-input--invalid' : ''} ${
          rest.disabled ? 'ds-input--disabled' : ''
        }`.trim()}
      >
        {prefix && <span className="ds-input-group__addon ds-input-group__addon--pre">{prefix}</span>}
        <input id={id} className={`ds-input ds-input--grouped ${className}`.trim()} {...rest} />
        {suffix && <span className="ds-input-group__addon ds-input-group__addon--post">{suffix}</span>}
      </div>
    )
  }
  return (
    <input
      id={id}
      className={`ds-input ${invalid ? 'ds-input--invalid' : ''} ${className}`.trim()}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  )
}

/* ===== Textarea ===== */
export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean
}

export function Textarea({ invalid, className = '', ...rest }: TextareaProps) {
  return (
    <textarea
      className={`ds-input ds-input--textarea ${invalid ? 'ds-input--invalid' : ''} ${className}`.trim()}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  )
}
