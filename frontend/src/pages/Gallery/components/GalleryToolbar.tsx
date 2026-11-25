import type { MutableRefObject } from 'react'
import { Button, Select } from '../../../components/ui'
import type { ImageSort } from '../../../types/workbench'
import type { GalleryCategory, GallerySeries, GallerySource } from '../hooks/useGalleryQuery'
import {
  DENSITY_OPTIONS,
  FIT_OPTIONS,
  LAYOUT_OPTIONS,
  type GalleryDensity,
  type GalleryFit,
  type GalleryLayout,
} from '../hooks/useGalleryPrefs'

/** 状态导航与审核入口由侧栏和页面标题栏承载；这里只保留视图、筛选和批量工具。 */

const SORT_OPTIONS: { value: ImageSort; label: string }[] = [
  { value: 'created_desc', label: '最新优先' },
  { value: 'created_asc', label: '最早优先' },
  { value: 'favorite', label: '收藏优先' },
  { value: 'size', label: '尺寸优先' },
]

const SOURCE_OPTIONS: { value: GallerySource; label: string }[] = [
  { value: '', label: '来源：全部' },
  { value: 'comfyui', label: '生成' },
  { value: 'import', label: 'V1 导入' },
]

/** 分类：动漫 = anime_generate 产物 + V1 导入的 Anima 输出；导入 = 全部外部导入。 */
const CATEGORY_OPTIONS: { value: GalleryCategory; label: string }[] = [
  { value: '', label: '分类：全部' },
  { value: 'anime', label: '动漫' },
  { value: 'imported', label: '导入' },
]

interface GalleryToolbarProps {
  view: 'flat' | 'group'
  onToggleView: () => void
  source: GallerySource
  onSourceChange: (value: GallerySource) => void
  category: GalleryCategory
  onCategoryChange: (value: GalleryCategory) => void
  series: GallerySeries
  onSeriesChange: (value: GallerySeries) => void
  seriesOptions: { series: string; count: number }[]
  sort: ImageSort
  onSortChange: (value: ImageSort) => void
  density: GalleryDensity
  onDensityChange: (value: GalleryDensity) => void
  layout: GalleryLayout
  onLayoutChange: (value: GalleryLayout) => void
  fit: GalleryFit
  onFitChange: (value: GalleryFit) => void
  selectMode: boolean
  onToggleSelect: () => void
  cleanupBusy: boolean
  onOpenCleanup: () => void
  importProgress: { done: number; total: number } | null
  importInputRef: MutableRefObject<HTMLInputElement | null>
  onImportChange: (event: React.ChangeEvent<HTMLInputElement>) => void
}

export function GalleryToolbar({
  view, onToggleView,
  source, onSourceChange, sort, onSortChange,
  category, onCategoryChange,
  series, onSeriesChange, seriesOptions,
  density, onDensityChange, layout, onLayoutChange, fit, onFitChange,
  selectMode, onToggleSelect,
  cleanupBusy, onOpenCleanup, importProgress, importInputRef, onImportChange,
}: GalleryToolbarProps) {
  return (
    <div className="gal-toolbar gal-toolbar--filters">
      <div className="gal-segmented" role="group" aria-label="视图切换">
        <Button
          size="sm" variant={view === 'flat' ? 'primary' : 'secondary'}
          onClick={() => view !== 'flat' && onToggleView()}
        >
          网格
        </Button>
        <Button
          size="sm" variant={view === 'group' ? 'primary' : 'secondary'}
          onClick={() => view !== 'group' && onToggleView()}
        >
          按任务查看
        </Button>
      </div>
      <Select
          aria-label="分类"
          value={category}
          onChange={(event) => onCategoryChange(event.target.value as GalleryCategory)}
          options={CATEGORY_OPTIONS.map(({ value, label }) => ({ value, label }))}
      />
      {/* 0024：系列（如「末世后宫」）；候选项由 /api/v1/images/series 动态提供 */}
      <Select
          aria-label="系列"
          value={series}
          onChange={(event) => onSeriesChange(event.target.value)}
          options={[
            { value: '', label: '系列：全部' },
            ...seriesOptions.map(({ series: name, count }) => ({
              value: name,
              label: `${name}（${count}）`,
            })),
            ...(series && !seriesOptions.some((option) => option.series === series)
              ? [{ value: series, label: series }]
              : []),
          ]}
      />
      <Select
          aria-label="来源"
          value={source}
          onChange={(event) => onSourceChange(event.target.value as GallerySource)}
          options={SOURCE_OPTIONS.map(({ value, label }) => ({ value, label }))}
      />
      <Select
          aria-label="排序"
          value={sort}
          onChange={(event) => onSortChange(event.target.value as ImageSort)}
          options={SORT_OPTIONS.map(({ value, label }) => ({ value, label }))}
      />
      <Select
          aria-label="网格密度"
          value={density}
          onChange={(event) => onDensityChange(event.target.value as GalleryDensity)}
          options={DENSITY_OPTIONS.map(({ value, label }) => ({ value, label }))}
      />
      <Select
          aria-label="图库布局"
          value={layout}
          onChange={(event) => onLayoutChange(event.target.value as GalleryLayout)}
          options={LAYOUT_OPTIONS.map(({ value, label }) => ({ value, label }))}
      />
      <Select
          aria-label="图片适应"
          value={fit}
          onChange={(event) => onFitChange(event.target.value as GalleryFit)}
          options={FIT_OPTIONS.map(({ value, label }) => ({ value, label }))}
      />

      <span className="gal-toolbar__spacer" />

      <Button
        size="sm" variant={selectMode ? 'primary' : 'secondary'}
        onClick={onToggleSelect}
      >
        {selectMode ? '退出选择' : '选择'}
      </Button>
      <Button
        size="sm" variant="secondary"
        disabled={importProgress !== null}
        onClick={() => importInputRef.current?.click()}
      >
        {importProgress ? `导入中 ${importProgress.done} / ${importProgress.total}` : '导入'}
      </Button>
      <Button size="sm" variant="danger" disabled={cleanupBusy} onClick={onOpenCleanup}>
        {cleanupBusy ? '准备中…' : '清理废片'}
      </Button>

      <input
        ref={importInputRef}
        type="file"
        accept=".jpg,.jpeg,.png,.webp"
        multiple
        hidden
        onChange={(event) => onImportChange(event)}
      />
    </div>
  )
}
