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
  onCancel: () => void
  onConfirm: () => void
}

export function CleanupRejectedDialog({ preview, busy, onCancel, onConfirm }: CleanupRejectedDialogProps) {
  return (
    <Modal
      open={preview !== null}
      onClose={onCancel}
      title="清理废片（REJECT）"
      footer={
        <>
          <Button size="sm" variant="secondary" onClick={onCancel}>
            取消
          </Button>
          <Button
            size="sm" variant="danger"
            disabled={busy || (preview?.deletable_count ?? 0) === 0}
            onClick={() => void onConfirm()}
          >
            {busy ? '删除中…' : `确认删除 ${preview?.deletable_count ?? 0} 张`}
          </Button>
        </>
      }
    >
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
        <p className="muted" role="status">数量较多，删除可能需要数十秒，请勿关闭页面。</p>
      )}
    </Modal>
  )
}
