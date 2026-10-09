import type { KeyboardEvent, ReactNode } from 'react'

export interface TabItem {
  key: string
  label: ReactNode
  disabled?: boolean
}

export interface TabsProps {
  items: TabItem[]
  active: string
  onChange: (key: string) => void
  className?: string
  ariaLabel?: string
}

export function Tabs({ items, active, onChange, className = '', ariaLabel }: TabsProps) {
  const onKeyDown = (e: KeyboardEvent) => {
    const enabled = items.filter((i) => !i.disabled)
    const idx = enabled.findIndex((i) => i.key === active)
    if (idx < 0) return
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
      e.preventDefault()
      const next =
        e.key === 'ArrowRight'
          ? enabled[(idx + 1) % enabled.length]
          : enabled[(idx - 1 + enabled.length) % enabled.length]
      onChange(next.key)
    }
  }
  return (
    <div className={`ds-tabs ${className}`.trim()} role="tablist" aria-label={ariaLabel} onKeyDown={onKeyDown}>
      {items.map((i) => {
        const isActive = i.key === active
        return (
          <button
            key={i.key}
            type="button"
            role="tab"
            id={`tab-${i.key}`}
            aria-selected={isActive}
            aria-controls={`tabpanel-${i.key}`}
            tabIndex={isActive ? 0 : -1}
            disabled={i.disabled}
            className={`ds-tabs__item ${isActive ? 'ds-tabs__item--active' : ''}`.trim()}
            onClick={() => onChange(i.key)}
          >
            {i.label}
          </button>
        )
      })}
    </div>
  )
}

export function TabPanel({ itemKey, active, children, className = '' }: { itemKey: string; active: string; children: ReactNode; className?: string }) {
  return (
    <div
      id={`tabpanel-${itemKey}`}
      role="tabpanel"
      aria-labelledby={`tab-${itemKey}`}
      hidden={itemKey !== active}
      className={className}
    >
      {children}
    </div>
  )
}
