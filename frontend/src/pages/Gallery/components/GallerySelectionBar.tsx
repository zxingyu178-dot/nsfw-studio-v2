import { Badge, Button } from '../../../components/ui'

/**
 * Phase 0.12 Task6：多选 sticky 操作条。
 * 已选 N 张 → [高清放大][保留][淘汰][归档][收藏][取消选择]；审核状态走批量审核 API，
 * 收藏逐条 favorite。进入选择模式后替代第二条普通 Toolbar。
 */

interface GallerySelectionBarProps {
  count: number
  upscaling: boolean
  selectingAll: boolean
  busy: boolean
  onSelectAll: () => void
  onUpscale: () => void
  onBatchKeep: () => void
  onBatchReject: () => void
  onBatchArchive: () => void
  onBatchFavorite: () => void
  onExitSelect: () => void
}

export function GallerySelectionBar({
  count, upscaling, selectingAll, busy, onSelectAll, onUpscale, onBatchKeep, onBatchReject, onBatchArchive,
  onBatchFavorite, onExitSelect,
}: GallerySelectionBarProps) {
  const none = count === 0
  return (
    <div className="gal-selection-bar">
      <Badge tone="accent">已选 {count} 张</Badge>
      <div className="gal-selection-bar__actions">
        <Button size="sm" variant="secondary" disabled={selectingAll || busy} onClick={onSelectAll}>
          {selectingAll ? '选择中…' : '全选当前筛选'}
        </Button>
        <Button size="sm" variant="primary" disabled={upscaling || busy || none} onClick={onUpscale}>
          {upscaling ? '提交中…' : '高清放大'}
        </Button>
        <Button size="sm" variant="secondary" disabled={busy || none} onClick={onBatchKeep}>
          保留
        </Button>
        <Button size="sm" variant="secondary" disabled={busy || none} onClick={onBatchReject}>
          淘汰
        </Button>
        <Button size="sm" variant="secondary" disabled={busy || none} onClick={onBatchArchive}>
          归档
        </Button>
        <Button size="sm" variant="secondary" disabled={busy || none} onClick={onBatchFavorite}>
          收藏
        </Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={onExitSelect}>
          取消选择
        </Button>
      </div>
    </div>
  )
}
