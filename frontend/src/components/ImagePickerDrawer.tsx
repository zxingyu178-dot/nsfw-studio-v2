import { useCallback, useEffect, useState } from 'react'
import { ApiRequestError, imageApi } from '../api/client'
import { IMAGE_KIND_LABEL, imageContentUrl, type ImageDTO } from '../types/workbench'

type PickerFilter = 'RECENT' | 'UNREVIEWED' | 'KEPT' | 'FAVORITE'

const FILTERS: { key: PickerFilter; label: string }[] = [
  { key: 'RECENT', label: '最近' },
  { key: 'UNREVIEWED', label: '未审核' },
  { key: 'KEPT', label: '保留' },
  { key: 'FAVORITE', label: '收藏' },
]

interface ImagePickerDrawerProps {
  title?: string
  onClose: () => void
  onPicked: (image: ImageDTO) => void
}

/** 图库图片选择器（Phase 5 §二十一）：筛选（最近/未审核/保留/收藏）+ 搜索导入文件名；
 * 卡片只展示缩略图 / 尺寸 / 收藏；选择后返回调用方。 */
export function ImagePickerDrawer({ title = '从图库选择图片', onClose, onPicked }: ImagePickerDrawerProps) {
  const [filter, setFilter] = useState<PickerFilter>('RECENT')
  const [search, setSearch] = useState('')
  const [items, setItems] = useState<ImageDTO[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    imageApi
      .list({
        review_status: filter === 'UNREVIEWED' ? 'UNREVIEWED' : filter === 'KEPT' ? 'KEPT' : null,
        favorite: filter === 'FAVORITE' ? true : null,
        search: search.trim() || null,
        limit: 120,
      })
      .then((page) => setItems(page.items))
      .catch((err: unknown) => setError(err instanceof ApiRequestError ? err.message : '加载图片失败'))
      .finally(() => setLoading(false))
  }, [filter, search])

  useEffect(() => {
    const timer = window.setTimeout(load, 200)
    return () => window.clearTimeout(timer)
  }, [load])

  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="drawer drawer--wide"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drawer__header">
          <h3 className="drawer__title">{title}</h3>
          <button type="button" className="btn btn--ghost btn--sm" onClick={onClose} aria-label="关闭">
            ✕
          </button>
        </header>

        <div className="tabs" role="tablist" aria-label="图片筛选">
          {FILTERS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={filter === key}
              className={`tabs__item${filter === key ? ' tabs__item--active' : ''}`}
              onClick={() => setFilter(key)}
            >
              {label}
            </button>
          ))}
        </div>

        <input
          className="input drawer__search"
          placeholder="搜索导入文件名"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />

        {loading && <p className="muted">加载中…</p>}
        {error && <p className="notice notice--error">{error}</p>}
        {!loading && !error && items.length === 0 && <p className="muted">没有符合条件的图片。</p>}

        <div className="image-picker__grid">
          {items.map((image) => (
            <button
              key={image.id}
              type="button"
              className="image-picker__item"
              title={`${IMAGE_KIND_LABEL[image.kind] ?? image.kind} · ${image.width}×${image.height}`}
              onClick={() => onPicked(image)}
            >
              <img src={imageContentUrl(image.id)} alt="" loading="lazy" />
              <span className="image-picker__meta">
                {image.width}×{image.height}
                {image.favorite && <span title="已收藏"> ★</span>}
              </span>
            </button>
          ))}
        </div>
      </aside>
    </div>
  )
}