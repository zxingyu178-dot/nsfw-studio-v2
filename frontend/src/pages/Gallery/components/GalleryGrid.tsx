import { useEffect, useMemo, useRef, useState, type MutableRefObject } from 'react'
import type { ImageDTO } from '../../../types/workbench'
import type { GalleryDensity, GalleryFit, GalleryLayout } from '../hooks/useGalleryPrefs'
import { distributeColumns } from '../lib/distributeColumns'
import { GalleryCard } from './GalleryCard'

/**
 * Phase 0.12 Task6：图片网格。密度（小/中/大）与适应方式（contain/cover）作为
 * 修饰类作用于 .gal-grid，CSS 据此切换列宽与媒体框行为。
 *
 * v0.37 P1-B：默认「整齐网格」——真正的 CSS Grid，统一媒体框、逐行对齐；
 * 「瀑布流」沿用原有最矮列分配算法。
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
  layout: GalleryLayout
  onCardClick: (image: ImageDTO) => void
  onCardDoubleClick: (image: ImageDTO) => void
  onToggleFavorite: (image: ImageDTO) => void
  sentinelRef: MutableRefObject<HTMLDivElement | null>
}

export function GalleryGrid({
  items, total, hasNext, loading, loadingMore, selectedIds, selectMode,
  density, fit, layout, onCardClick, onCardDoubleClick, onToggleFavorite, sentinelRef,
}: GalleryGridProps) {
  const gridRef = useRef<HTMLDivElement | null>(null)
  const [columnCount, setColumnCount] = useState(1)

  useEffect(() => {
    if (layout !== 'waterfall') return
    const element = gridRef.current
    if (!element) return
    const targetWidth = density === 'compact' ? 170 : density === 'large' ? 280 : 220
    const update = (width: number) => {
      setColumnCount(Math.max(1, Math.floor((width + 12) / (targetWidth + 12))))
    }
    update(element.clientWidth)
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) => {
      update(entries[0]?.contentRect.width ?? element.clientWidth)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [density, layout])

  const columns = useMemo(
    () => distributeColumns(items, columnCount, imageAspect),
    [items, columnCount],
  )

  const cardProps = {
    selectMode,
    layout,
    onCardClick,
    onCardDoubleClick,
    onToggleFavorite,
  }

  const renderCard = (image: ImageDTO) => (
    <GalleryCard
      key={image.id}
      image={image}
      selected={selectedIds.includes(image.id)}
      {...cardProps}
    />
  )

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
      <div
        ref={gridRef}
        className={`gal-grid gal-grid--${density} gal-grid--fit-${fit} gal-grid--layout-${layout}`}
      >
        {layout === 'grid'
          ? items.map(renderCard)
          : columns.map((column, columnIndex) => (
              <div className="gal-col" key={columnIndex}>
                {column.map(renderCard)}
              </div>
            ))}
      </div>
      {/* 无限滚动哨兵 */}
      {hasNext && <div ref={sentinelRef} className="gal-sentinel" aria-hidden="true" />}
      {loadingMore && <p className="muted">加载更多…</p>}
    </>
  )
}

function imageAspect(image: ImageDTO): number {
  // 相对高度 = height / width（竖图更大），用于"放进当前最矮列"的估算。
  return image.width > 0 && image.height > 0 ? image.height / image.width : 1
}
