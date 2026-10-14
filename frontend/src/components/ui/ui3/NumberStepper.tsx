/**
 * UI3 NumberStepper —— − / 数值 / + 步进器。
 *
 * - min/max 钳制（步进与直接输入都钳制）；
 * - 中间为可键盘输入的数字框，失焦 / Enter 时解析并钳制；
 * - 可选快捷 chips（如 1/2/4/6/8）。
 */
import { useEffect, useState, type ClipboardEvent, type KeyboardEvent } from 'react'
import { IconMinus, IconPlus } from './icons'

export interface NumberStepperProps {
  value: number
  onChange: (value: number) => void
  min?: number
  max?: number
  step?: number
  /** 快捷 chip（如 [1,2,4,6,8]）。 */
  chips?: number[]
  disabled?: boolean
  ariaLabel?: string
  className?: string
  /** 输入框聚焦 / 失焦回调（业务层用于“编辑中不被外部回灌打断”的脏标记）。 */
  onFocus?: () => void
  onBlur?: () => void
}

function clamp(v: number, min: number, max: number) {
  return Math.min(max, Math.max(min, v))
}

export function NumberStepper({
  value,
  onChange,
  min = Number.MIN_SAFE_INTEGER,
  max = Number.MAX_SAFE_INTEGER,
  step = 1,
  chips,
  disabled,
  ariaLabel,
  className = '',
  onFocus,
  onBlur,
}: NumberStepperProps) {
  const [draft, setDraft] = useState(String(value))

  // 外部 value 变化时同步输入框（仅当未处于编辑态）
  useEffect(() => {
    setDraft(String(value))
  }, [value])

  const commit = (raw: string) => {
    const n = Number(raw)
    if (Number.isFinite(n)) onChange(clamp(Math.round(n), min, max))
    else setDraft(String(value))
  }

  const bump = (dir: 1 | -1) => onChange(clamp(value + dir * step, min, max))

  const onInputKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      commit(draft)
      ;(e.target as HTMLInputElement).blur()
    } else if (e.key === 'Escape') {
      setDraft(String(value))
      ;(e.target as HTMLInputElement).blur()
    }
  }

  const onPaste = (e: ClipboardEvent<HTMLInputElement>) => e.preventDefault()

  const atMin = value <= min
  const atMax = value >= max

  return (
    <div className={`ui3-stepper ${className}`.trim()} role="group" aria-label={ariaLabel ?? '数值步进器'}>
      <div className="ui3-stepper__control">
        <button
          type="button"
          className="ui3-stepper__btn"
          aria-label="减"
          disabled={disabled || atMin}
          onClick={() => bump(-1)}
        >
          <IconMinus size={14} />
        </button>
        <input
          className="ui3-stepper__input"
          inputMode="numeric"
          aria-label={ariaLabel ?? '数值'}
          value={draft}
          disabled={disabled}
          onChange={(e) => setDraft(e.target.value)}
          onFocus={() => onFocus?.()}
          onBlur={() => {
            commit(draft)
            onBlur?.()
          }}
          onKeyDown={onInputKey}
          onPaste={onPaste}
        />
        <button
          type="button"
          className="ui3-stepper__btn"
          aria-label="加"
          disabled={disabled || atMax}
          onClick={() => bump(1)}
        >
          <IconPlus size={14} />
        </button>
      </div>
      {chips && chips.length > 0 && (
        <div className="ui3-stepper__chips">
          {chips.map((c) => (
            <button
              key={c}
              type="button"
              className={[
                'ui3-stepper__chip',
                c === value ? 'ui3-stepper__chip--active' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              aria-pressed={c === value}
              disabled={disabled || c < min || c > max}
              onClick={() => onChange(clamp(c, min, max))}
            >
              {c}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
