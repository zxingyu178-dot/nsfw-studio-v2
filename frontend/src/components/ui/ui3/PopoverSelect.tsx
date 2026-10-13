/**
 * UI3 PopoverSelect —— 替代原生 <select> 的自定义下拉。
 *
 * ARIA：触发器 button + aria-haspopup="listbox" + aria-expanded；
 *       浮层 role="listbox"；每项 role="option" + aria-selected。
 * 键盘：↑/↓ 移动高亮、Enter 选中、Esc 关闭、输入字符 typeahead 前缀匹配；
 *       点击外部关闭。受控 value/onChange。
 *
 * 禁止在业务页再用原生 <select>（primitive 内部例外）。
 */
import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { IconChevronDown } from './icons'

export interface PopoverOption<T extends string = string> {
  value: T
  label: ReactNode
  /** 行首图标（可选）。 */
  icon?: ReactNode
  disabled?: boolean
  /** typeahead 检索文本；缺省用 label（label 为字符串时）。 */
  searchText?: string
}

export interface PopoverSelectProps<T extends string = string> {
  value: T
  onChange: (value: T) => void
  options: PopoverOption<T>[]
  placeholder?: ReactNode
  /** 触发器行首图标（与行内 option icon 区分）。 */
  leadingIcon?: ReactNode
  disabled?: boolean
  className?: string
  ariaLabel?: string
}

function enabledIndex<T extends string>(
  options: PopoverOption<T>[],
  from: number,
  dir: 1 | -1,
): number {
  const n = options.length
  if (n === 0) return -1
  let i = from
  for (let step = 0; step < n; step++) {
    i = (i + dir + n) % n
    if (!options[i].disabled) return i
  }
  return from
}

export function PopoverSelect<T extends string = string>({
  value,
  onChange,
  options,
  placeholder = '请选择',
  leadingIcon,
  disabled,
  className = '',
  ariaLabel,
}: PopoverSelectProps<T>) {
  const rootRef = useRef<HTMLDivElement>(null)
  const listId = useId()
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const bufferRef = useRef('')
  const bufferTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const selectedIndex = options.findIndex((o) => o.value === value)
  const selected = selectedIndex >= 0 ? options[selectedIndex] : undefined

  const openList = () => {
    if (disabled) return
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : enabledIndex(options, -1, 1))
    setOpen(true)
  }
  const closeList = () => setOpen(false)

  // 点击外部关闭
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) closeList()
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  useEffect(
    () => () => {
      if (bufferTimer.current) clearTimeout(bufferTimer.current)
    },
    [],
  )

  const choose = (index: number) => {
    const opt = options[index]
    if (!opt || opt.disabled) return
    onChange(opt.value)
    closeList()
  }

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return
    switch (e.key) {
      case 'ArrowDown':
      case 'ArrowUp': {
        e.preventDefault()
        if (!open) {
          openList()
        } else {
          const dir = e.key === 'ArrowDown' ? 1 : -1
          setActiveIndex((cur) => enabledIndex(options, cur < 0 ? -1 : cur, dir))
        }
        break
      }
      case 'Enter':
      case ' ': {
        e.preventDefault()
        if (!open) openList()
        else if (activeIndex >= 0) choose(activeIndex)
        break
      }
      case 'Escape': {
        if (open) {
          e.stopPropagation()
          closeList()
        }
        break
      }
      case 'Tab': {
        closeList()
        break
      }
      default: {
        // typeahead：可打印字符前缀匹配
        if (open && e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
          e.preventDefault()
          bufferRef.current = (bufferRef.current + e.key).toLowerCase()
          if (bufferTimer.current) clearTimeout(bufferTimer.current)
          bufferTimer.current = setTimeout(() => (bufferRef.current = ''), 600)
          const hit = options.findIndex(
            (o) =>
              !o.disabled &&
              (o.searchText ?? (typeof o.label === 'string' ? o.label : '')).toLowerCase()
                .startsWith(bufferRef.current),
          )
          if (hit >= 0) setActiveIndex(hit)
        }
      }
    }
  }

  const classes = ['ui3-select', open ? 'ui3-select--open' : '', className]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={classes} ref={rootRef} onKeyDown={onKeyDown}>
      <button
        type="button"
        className="ui3-select__trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => (open ? closeList() : openList())}
      >
        {leadingIcon && <span className="ui3-select__lead">{leadingIcon}</span>}
        <span className="ui3-select__value">
          {selected ? (
            <>
              {selected.icon && <span className="ui3-select__opt-icon">{selected.icon}</span>}
              {selected.label}
            </>
          ) : (
            <span className="ui3-select__placeholder">{placeholder}</span>
          )}
        </span>
        <IconChevronDown size={14} className="ui3-select__chevron" />
      </button>

      {open && (
        <ul className="ui3-select__list" id={listId} role="listbox">
          {options.map((opt, i) => (
            <li
              key={opt.value}
              role="option"
              aria-selected={opt.value === value}
              aria-disabled={opt.disabled || undefined}
              className={[
                'ui3-select__option',
                i === activeIndex ? 'ui3-select__option--active' : '',
                opt.value === value ? 'ui3-select__option--selected' : '',
                opt.disabled ? 'ui3-select__option--disabled' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              onMouseEnter={() => !opt.disabled && setActiveIndex(i)}
              onClick={() => choose(i)}
            >
              {opt.icon && <span className="ui3-select__opt-icon">{opt.icon}</span>}
              <span className="ui3-select__opt-label">{opt.label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
