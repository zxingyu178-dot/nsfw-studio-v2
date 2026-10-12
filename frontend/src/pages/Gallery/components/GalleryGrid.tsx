import type { MutableRefObject } from 'react'
import type { ImageDTO } from '../../../types/workbench'
import { GalleryCard } from './GalleryCard'

/**
 * Phase 0.12 Task9：图片网格（从 GalleryPage 抽取，行为不变）。
 * 含加载态 / 空态 / 计数 / 卡片网格 / 无限滚动哨兵。
 */

interface GalleryGridProps {
  items: ImageDTO[]
  total: number
  hasNext: boolean
  loading: boolean
  loadingMore: boolean
  selectedIds: string[]
  onCardClick: (image: ImageDTO) => void
  onCardDoubleClick: (image: ImageDTO) => void
  sentinelRef: MutableRefObject<HTMLDivElement | null>
}

export function GalleryGrid({
  items, total, hasNext, loading, loadingMore, selectedIds,
  onCardClick, onCardDoubleClick, sentinelRef,
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
      <div className="gal-grid">
        {items.map((image) => (
          <GalleryCard
            key={image.id}
            image={image}
            selected={selectedIds.includes(image.id)}
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
