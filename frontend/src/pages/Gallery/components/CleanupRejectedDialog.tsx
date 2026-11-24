import { Button, Modal } from '../../../components/ui'
import { shortJobId, type CleanupRejectedResult } from '../../../types/workbench'

/**
 * Phase 0.12 Task9：废片清理两阶段确认对话框（从 GalleryPage 抽取，行为不变）。
 */

/** 人读字节数 */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

interface CleanupRejectedDialogProps {
  preview: CleanupRejectedResult | null
  busy: boolean
  /** v0.37.2：点击后立即开弹窗，先显示"统计中"，避免数秒无反馈被误判为无响应 */
  loading?: boolean
  /** v0.37.3：按批删除进度（done/total），让用户可以确认仍在推进 */
  progress?: { done: number; total: number } | null
  onCancel: () => void
  onConfirm: () => void
}

export function CleanupRejectedDialog({
  preview, busy, loading = false, progress = null, onCancel, onConfirm,
}: CleanupRejectedDialogProps) {
  return (
    <Modal
      open={loading || preview !== null}
      onClose={() => { if (!loading && !busy) onCancel() }}
      title="清理废片（REJECT）"
      footer={
        <>
          <Button size="sm" variant="secondary" disabled={loading || busy} onClick={onCancel}>
            取消
          </Button>
          <Button
            size="sm" variant="danger"
            disabled={loading || busy || (preview?.deletable_count ?? 0) === 0}
            onClick={() => void onConfirm()}
          >
            {loading ? '统计中…'
              : busy ? (progress ? `删除中 ${progress.done}/${progress.total}` : '删除中…')
              : `确认删除 ${preview?.deletable_count ?? 0} 张`}
          </Button>
        </>
      }
    >
      {loading ? (
        <p className="muted" role="status">正在统计可删除的淘汰图与占用空间，请稍候…</p>
      ) : (
        <>
          {busy && progress && (
            <p className="muted" role="status">
              正在分批删除：已处理 {progress.done} / {progress.total} 张，请勿关闭页面。
            </p>
          )}
          <p className="muted">将永久删除可删 REJECT 图片的 original + thumbnail 及数据库记录（不可恢复）。</p>
          <dl className="gal-fields">
            <dt>候选（全部 REJECT）</dt>
            <dd>{preview?.candidate_count ?? 0} 张</dd>
            <dt>实际可删</dt>
            <dd>{preview?.deletable_count ?? 0} 张</dd>
            <dt>预计释放</dt>
            <dd>{formatBytes(preview?.total_bytes ?? 0)}</dd>
            <dt>被引用保护</dt>
            <dd>{preview?.protected_count ?? 0} 张（被 Prompt / 素材 / 配方引用，不会删除）</dd>
          </dl>
          {(preview?.protected_items?.length ?? 0) > 0 && (
            <details>
              <summary className="muted">查看受保护图片及原因</summary>
              <ul className="gal-protected-list">
                {preview?.protected_items?.map((item) => (
                  <li key={item.image_id}>
                    <span className="gal-protected__id">{shortJobId(item.image_id)}</span>
                    <span className="muted">{item.reasons.join('；')}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
          {(preview?.deletable_count ?? 0) >= 500 && (
            <p className="muted" role="status">数量较多，将分批删除并实时显示进度，请勿关闭页面。</p>
          )}
        </>
      )}
    </Modal>
  )
}
