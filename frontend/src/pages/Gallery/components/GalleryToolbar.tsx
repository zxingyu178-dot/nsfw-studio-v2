import type { MutableRefObject } from 'react'
import { Button, Select, Tabs } from '../../../components/ui'
import type { ImageReviewStatus, ImageSort } from '../../../types/workbench'
import type { TabKey } from '../hooks/useGalleryQuery'

/**
 * Phase 0.12 Task9：图库工具栏（从 GalleryPage 抽取，行为不变）。
 * 第一层浏览 Tab + 状态/排序 Select + 主操作按钮（开始审核/清理/选择/按任务/导入）。
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

interface GalleryToolbarProps {
  tab: TabKey
  onTabChange: (tab: TabKey) => void
  subStatus: '' | ImageReviewStatus
  onSubStatusChange: (value: '' | ImageReviewStatus) => void
  sort: ImageSort
  onSortChange: (value: ImageSort) => void
  selectMode: boolean
  onToggleSelect: () => void
  view: 'flat' | 'group'
  onToggleView: () => void
  onStartReview: () => void
  cleanupBusy: boolean
  onOpenCleanup: () => void
  importProgress: { done: number; total: number } | null
  importInputRef: MutableRefObject<HTMLInputElement | null>
  onImportChange: (event: React.ChangeEvent<HTMLInputElement>) => void
}

export function GalleryToolbar({
  tab, onTabChange, subStatus, onSubStatusChange, sort, onSortChange,
  selectMode, onToggleSelect, view, onToggleView, onStartReview,
  cleanupBusy, onOpenCleanup, importProgress, importInputRef, onImportChange,
}: GalleryToolbarProps) {
  return (
    <div className="gal-toolbar">
      <Tabs
        ariaLabel="图库筛选"
        active={tab}
        onChange={(key) => onTabChange(key as TabKey)}
        items={TABS.map(({ key, label }) => ({ key, label }))}
      />
      <Select
        aria-label="审核状态细分"
        value={subStatus}
        onChange={(event) => onSubStatusChange(event.target.value as '' | ImageReviewStatus)}
        options={SUB_STATUS_OPTIONS.map(({ value, label }) => ({ value, label }))}
      />
      <Select
        aria-label="排序"
        value={sort}
        onChange={(event) => onSortChange(event.target.value as ImageSort)}
        options={SORT_OPTIONS.map(({ value, label }) => ({ value, label }))}
      />
      <span className="gal-toolbar__spacer" />
      <Button size="sm" variant="primary" onClick={onStartReview}>
        开始审核
      </Button>
      <Button size="sm" variant="danger" disabled={cleanupBusy} onClick={() => void onOpenCleanup()}>
        {cleanupBusy ? '准备中…' : '清理废片'}
      </Button>
      <Button
        size="sm" variant={selectMode ? 'primary' : 'secondary'}
        onClick={onToggleSelect}
      >
        {selectMode ? '退出选择' : '选择'}
      </Button>
      <Button
        size="sm" variant={view === 'group' ? 'primary' : 'secondary'}
        onClick={onToggleView}
      >
        按任务查看
      </Button>
      <Button
        size="sm" variant="secondary"
        disabled={importProgress !== null}
        onClick={() => importInputRef.current?.click()}
      >
        {importProgress ? `导入中 ${importProgress.done} / ${importProgress.total}` : '导入'}
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
