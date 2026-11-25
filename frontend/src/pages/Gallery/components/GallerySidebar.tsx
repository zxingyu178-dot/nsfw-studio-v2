import type { ImageReviewStatus } from '../../../types/workbench'
import type { TabKey } from '../hooks/useGalleryQuery'

export type GallerySidebarKey = TabKey | Extract<ImageReviewStatus, 'KEEP' | 'REJECT'>

interface GallerySidebarProps {
  active: GallerySidebarKey
  total: number
  onChange: (key: GallerySidebarKey) => void
}

const ITEMS: { key: GallerySidebarKey; icon: string; label: string }[] = [
  { key: 'ALL', icon: '▧', label: '全部图片' },
  { key: 'NEW', icon: '◌', label: '待审图片' },
  { key: 'KEEP', icon: '✓', label: '已保留' },
  { key: 'REJECT', icon: '×', label: '废片' },
  { key: 'FAVORITE', icon: '☆', label: '收藏图片' },
  { key: 'ARCHIVED', icon: '□', label: '已归档' },
]

export function GallerySidebar({ active, total, onChange }: GallerySidebarProps) {
  return (
    <aside className="gal-workspace__sidebar">
      <nav aria-label="图库分类" className="gal-sidebar-nav">
        {ITEMS.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`gal-sidebar-link${active === item.key ? ' gal-sidebar-link--active' : ''}`}
            aria-label={item.label}
            aria-current={active === item.key ? 'page' : undefined}
            onClick={() => onChange(item.key)}
          >
            <span className="gal-sidebar-link__icon" aria-hidden="true">{item.icon}</span>
            <span>{item.label}</span>
            {active === item.key && <span className="gal-sidebar-link__count">{total}</span>}
          </button>
        ))}
      </nav>
    </aside>
  )
}
