import { Badge, Button } from '../../../components/ui'

/**
 * Phase 0.12 Task9：多选操作条（从 GalleryPage 抽取，行为不变）。
 * 显示已选数量 + 高清放大入口。
 */

interface GallerySelectionBarProps {
  count: number
  upscaling: boolean
  onUpscale: () => void
}

export function GallerySelectionBar({ count, upscaling, onUpscale }: GallerySelectionBarProps) {
  return (
    <div className="gal-toolbar">
      <Badge tone="accent">已选 {count} 张</Badge>
      <Button
        size="sm" variant="primary"
        disabled={upscaling || count === 0}
        onClick={onUpscale}
      >
        {upscaling ? '提交中…' : '高清放大'}
      </Button>
      <span className="muted">选择图库已有图片（可多张）→ 创建高清任务，不重复生成原图。</span>
    </div>
  )
}
