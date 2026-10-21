import { useState, type MutableRefObject } from 'react'
import { Button, Select, Tabs } from '../../../components/ui'
import type { ImageReviewStatus, ImageSort } from '../../../types/workbench'
import type { GallerySource, TabKey } from '../hooks/useGalleryQuery'
import { DENSITY_OPTIONS, type GalleryDensity } from '../hooks/useGalleryPrefs'

/**
 * Phase 0.12 Task4：Gallery Toolbar 2.0 两层结构。
 * - 第一层（浏览模式）：全部|待审核|收藏|归档，右侧 网格/按任务 切换。
 * - 第二层（筛选操作）：左 状态/排序/网格密度/适应|填充；右 开始审核/选择/导入/更多▾。
 *   危险操作「清理废片」收进「更多/维护」，不再长期以红色主按钮抢视觉。
 */

const TABS: { key: TabKey; label: string }[] = [
  { key: 'ALL', label: '全部' },
  { key: 'NEW', label: '待审核' },
  { key: 'FAVORITE', label: '收藏' },
  { key: 'ARCHIVED', label: '归档' },
]

const SORT_OPTIONS: { value: ImageSort; label: string }[] = [
  { value: 'created_desc', label: '最新优先' },
  { value: 'created_asc', label: '最早优先' },
  { value: 'favorite', label: '收藏优先' },
  { value: 'size', label: '尺寸优先' },
]

/** 细分子筛选：在主 Tab 之上叠加 KEEP / REJECT 过滤 */
const SUB_STATUS_OPTIONS: { value: '' | ImageReviewStatus; label: string }[] = [
  { value: '', label: '状态：全部' },
  { value: 'KEEP', label: '保留' },
  { value: 'REJECT', label: '淘汰' },
]

const SOURCE_OPTIONS: { value: GallerySource; label: string }[] = [
  { value: '', label: '来源：全部' },
  { value: 'comfyui', label: '生成' },
  { value: 'import', label: 'V1 导入' },
]

interface GalleryToolbarProps {
  tab: TabKey
  onTabChange: (tab: TabKey) => void
  view: 'flat' | 'group'
  onToggleView: () => void
  subStatus: '' | ImageReviewStatus
  onSubStatusChange: (value: '' | ImageReviewStatus) => void
  source: GallerySource
  onSourceChange: (value: GallerySource) => void
  sort: ImageSort
  onSortChange: (value: ImageSort) => void
  density: GalleryDensity
  onDensityChange: (value: GalleryDensity) => void
  selectMode: boolean
  onToggleSelect: () => void
  onStartReview: () => void
  cleanupBusy: boolean
  onOpenCleanup: () => void
  importProgress: { done: number; total: number } | null
  importInputRef: MutableRefObject<HTMLInputElement | null>
  onImportChange: (event: React.ChangeEvent<HTMLInputElement>) => void
}

export function GalleryToolbar({
  tab, onTabChange, view, onToggleView,
  subStatus, onSubStatusChange, source, onSourceChange, sort, onSortChange,
  density, onDensityChange,
  selectMode, onToggleSelect, onStartReview,
  cleanupBusy, onOpenCleanup, importProgress, importInputRef, onImportChange,
}: GalleryToolbarProps) {
  const [moreOpen, setMoreOpen] = useState(false)

  return (
    <>
      {/* 第一层：浏览模式 */}
      <div className="gal-toolbar gal-toolbar--mode">
        <Tabs
          ariaLabel="图库筛选"
          active={tab}
          onChange={(key) => onTabChange(key as TabKey)}
          items={TABS.map(({ key, label }) => ({ key, label }))}
        />
        <span className="gal-toolbar__spacer" />
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
      </div>

      {/* 第二层：筛选与操作 */}
      <div className="gal-toolbar gal-toolbar--filters">
        <Select
          aria-label="审核状态细分"
          value={subStatus}
          onChange={(event) => onSubStatusChange(event.target.value as '' | ImageReviewStatus)}
          options={SUB_STATUS_OPTIONS.map(({ value, label }) => ({ value, label }))}
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

        <span className="gal-toolbar__spacer" />

        <Button size="sm" variant="primary" onClick={onStartReview}>
          开始审核
        </Button>
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

        <div className="gal-more">
          <Button size="sm" variant="secondary" onClick={() => setMoreOpen((open) => !open)} aria-expanded={moreOpen}>
            更多 ▾
          </Button>
          <div className={`gal-more__menu${moreOpen ? '' : ' gal-more__menu--closed'}`}>
            <Button
              size="sm" variant="danger" disabled={cleanupBusy}
              onClick={() => { setMoreOpen(false); void onOpenCleanup() }}
            >
              {cleanupBusy ? '准备中…' : '清理废片'}
            </Button>
          </div>
        </div>

        <input
          ref={importInputRef}
          type="file"
          accept=".jpg,.jpeg,.png,.webp"
          multiple
          hidden
          onChange={(event) => onImportChange(event)}
        />
      </div>
    </>
  )
}
