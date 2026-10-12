import type { MutableRefObject } from 'react'
import type { ImageDTO } from '../../../types/workbench'
import type { GalleryDensity, GalleryFit } from '../hooks/useGalleryPrefs'
import { GalleryCard } from './GalleryCard'

/**
 * Phase 0.12 Task6：图片网格。密度（小/中/大）与适应方式（contain/cover）作为
 * 修饰类作用于 .gal-grid，CSS 据此切换 minmax 列宽与媒体框高度/object-fit。
 */

interface GalleryGridProps {
  items: ImageDTO[]
  total: number
  hasNext: boolean
  loading: boolean
  loadingMore: boolean
  selectedIds: string[]
  selectMode: boolean
  density: GalleryDensity
  fit: GalleryFit
  onCardClick: (image: ImageDTO) => void
  onCardDoubleClick: (image: ImageDTO) => void
  sentinelRef: MutableRefObject<HTMLDivElement | null>
}

export function GalleryGrid({
  items, total, hasNext, loading, loadingMore, selectedIds, selectMode,
  density, fit, onCardClick, onCardDoubleClick, sentinelRef,
}: GalleryGridProps) {
  return (
    <>
      {loading && <p className="muted">加载中…</p>}
      {!loading && items.length === 0 && (
        <div className="gal-empty">
          <h2 className="gal-empty__title">还没有图片</h2>
          <p className="muted">在生成工作台创建任务后，生成的图片会逐张进入这里。</p>
        </div>
      )}
      <p className="gal-count">共 {total} 张</p>
      <div className={`gal-grid gal-grid--${density} gal-grid--fit-${fit}`}>
        {items.map((image) => (
          <GalleryCard
            key={image.id}
            image={image}
            selected={selectedIds.includes(image.id)}
            selectMode={selectMode}
            onCardClick={onCardClick}
            onCardDoubleClick={onCardDoubleClick}
          />
        ))}
      </div>
      {/* 无限滚动哨兵 */}
      {hasNext && <div ref={sentinelRef} className="gal-sentinel" aria-hidden="true" />}
      {loadingMore && <p className="muted">加载更多…</p>}
    </>
  )
}
