import { useState, type ReactNode } from 'react'
import { DisclosureButton } from '../../../components/ui/ui3'

/**
 * 右栏 / 左栏可折叠分组（UI 3.0）：
 * - 折叠态只存浏览器 localStorage（UI 偏好，不入 DB）；
 * - 首次访问（无记录）默认展开；
 * - id 唯一，避免不同页面共用同一存储 key。
 *
 * 语义：头部为 ui3 DisclosureButton（原生 <button aria-expanded aria-controls>），
 * 不再用自造 div[role="button"][tabindex]。
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
  const bodyId = `wb-section-body-${id}`

  function toggle(): void {
    setOpen((prev) => {
      const next = !prev
      try {
        window.localStorage.setItem(STORAGE_PREFIX + id, next ? '1' : '0')
      } catch {
        // 隐私模式等写入失败不影响功能
      }
      return next
    })
  }

  return (
    <section className={`wb-section${open ? '' : ' wb-section--closed'}`}>
      <DisclosureButton
        className="wb-section__head"
        expanded={open}
        controlsId={bodyId}
        onClick={toggle}
      >
        <span className="wb-section__caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
        <span className="wb-section__title">{title}</span>
        {extra && <span className="wb-section__extra">{extra}</span>}
      </DisclosureButton>
      {open && (
        <div id={bodyId} className="wb-section__body">
          {children}
        </div>
      )}
    </section>
  )
}
