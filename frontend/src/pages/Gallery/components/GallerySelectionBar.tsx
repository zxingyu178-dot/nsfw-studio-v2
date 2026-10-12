import { Badge, Button } from '../../../components/ui'

/**
 * Phase 0.12 Task6：多选 sticky 操作条。
 * 已选 N 张 → [高清放大][保留][淘汰][收藏][取消选择]；保留/淘汰走批量审核 API，
 * 收藏逐条 favorite。进入选择模式后替代第二条普通 Toolbar。
 */

interface GallerySelectionBarProps {
  count: number
  upscaling: boolean
  onUpscale: () => void
  onBatchKeep: () => void
  onBatchReject: () => void
  onBatchFavorite: () => void
  onExitSelect: () => void
}

export function GallerySelectionBar({
  count, upscaling, onUpscale, onBatchKeep, onBatchReject, onBatchFavorite, onExitSelect,
}: GallerySelectionBarProps) {
  const none = count === 0
  return (
    <div className="gal-selection-bar">
      <Badge tone="accent">已选 {count} 张</Badge>
      <div className="gal-selection-bar__actions">
        <Button size="sm" variant="primary" disabled={upscaling || none} onClick={onUpscale}>
          {upscaling ? '提交中…' : '高清放大'}
        </Button>
        <Button size="sm" variant="secondary" disabled={none} onClick={onBatchKeep}>
          保留
        </Button>
        <Button size="sm" variant="secondary" disabled={none} onClick={onBatchReject}>
          淘汰
        </Button>
        <Button size="sm" variant="secondary" disabled={none} onClick={onBatchFavorite}>
          收藏
        </Button>
        <Button size="sm" variant="ghost" onClick={onExitSelect}>
          取消选择
        </Button>
      </div>
    </div>
  )
}
