import { Button, Modal } from '../../../components/ui'
import type { ReviewSessionSummaryDTO } from '../../../api/client'

interface ResumeReviewDialogProps {
  session: ReviewSessionSummaryDTO | null
  onResume: () => void
  onStartNew: () => void
  onCancel: () => void
}

/**
 * v0.37.4：发现未完成审核批次时的入口选择。
 *
 * 之前点「开始审核」直接静默恢复旧批次（可能是几周前的会话），用户会以为打开的是空白/旧内容；
 * 现在明确给出「继续上次」「新建一批」两条路，避免误操作。
 */
export function ResumeReviewDialog({
  session, onResume, onStartNew, onCancel,
}: ResumeReviewDialogProps) {
  const seen = session?.seen_count ?? 0
  const total = session?.total_count ?? 0
  const position = Math.min((session?.current_index ?? 0) + 1, Math.max(total, 1))
  return (
    <Modal
      open={session !== null}
      onClose={onCancel}
      title="开始审核"
      footer={
        <>
          <Button size="sm" variant="secondary" onClick={onCancel}>取消</Button>
          <Button size="sm" variant="secondary" onClick={onStartNew}>新建一批（仅新图）</Button>
          <Button size="sm" onClick={onResume}>继续上次审核</Button>
        </>
      }
    >
      {session && (
        <>
          <p>
            发现未完成的审核批次：已审 <strong>{seen}</strong> / {total} 张，上次停在第 {position} 张。
          </p>
          <p className="muted">
            继续上次：从断点接着审；新建一批：该批未审的 {Math.max(total - seen, 0)} 张不再入队，
            只把从未入过批的新图排进来（已审核结果不受影响）。
          </p>
        </>
      )}
    </Modal>
  )
}
