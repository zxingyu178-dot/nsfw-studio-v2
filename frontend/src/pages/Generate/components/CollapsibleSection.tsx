import { useState, type ReactNode } from 'react'

/**
 * 右栏可折叠分组（Phase 0.12 任务 5.3）：
 * - 折叠态只存浏览器 localStorage（UI 偏好，不入 DB；见规范 §13 小型 UI 偏好持久化）；
 * - 首次访问（无记录）默认展开，保证既有自动化查询与新手可见全部字段；
 * - id 唯一，避免不同页面共用同一存储 key。
 */
const STORAGE_PREFIX = 'generate-section:'

function readStored(id: string): boolean | null {
  try {
    const value = window.localStorage.getItem(STORAGE_PREFIX + id)
    if (value === '1') return true
    if (value === '0') return false
    return null
  } catch {
    return null
  }
}

export function CollapsibleSection({
  id,
  title,
  extra,
  children,
  defaultOpen = true,
}: {
  id: string
  title: ReactNode
  /** 标题右侧常驻信息（如队列计数徽标），不随折叠隐藏。 */
  extra?: ReactNode
  children: ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState<boolean>(() => readStored(id) ?? defaultOpen)

  function toggle(): void {
    const next = !open
    setOpen(next)
    try {
      window.localStorage.setItem(STORAGE_PREFIX + id, next ? '1' : '0')
    } catch {
      // 隐私模式等写入失败不影响功能
    }
  }

  return (
    <section className={`wb-section${open ? '' : ' wb-section--closed'}`}>
      <button
        type="button"
        className="wb-section__head"
        aria-expanded={open}
        onClick={toggle}
      >
        <span className="wb-section__caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
        <span className="wb-section__title">{title}</span>
        {extra && <span className="wb-section__extra">{extra}</span>}
      </button>
      {open && <div className="wb-section__body">{children}</div>}
    </section>
  )
}
