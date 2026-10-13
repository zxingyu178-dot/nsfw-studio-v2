import { useState, type DragEvent, type ReactNode } from 'react'
import { ConfirmModal, StatusBadge } from '../../../components/ui'
import { ActionButton, IconButton, IconCancel, IconPause, IconPrev, IconResume } from '../../../components/ui/ui3'
import {
  cancelJob,
  clearStaleJobs,
  pauseJob,
  pauseQueue,
  reorderQueue,
  resumeJob,
  resumeQueue,
  useJobStore,
} from '../../../stores/jobStore'
import { MODULE_LABEL, shortJobId, type JobDTO } from '../../../types/workbench'

/**
 * 队列面板（规范 §五十四）：队列标题 + 全局暂停/继续 + 自动暂停提示 + 固定高度内部滚动列表。
 * 拖拽排序（draggable + DnD handlers）、优先/暂停/取消与队列暂停/继续全部保留。
 * v0.13.2：新增"清理陈旧任务"（跨重启遗留 QUEUED/RUNNING/PAUSED/INTERRUPTED → CANCELLED，不删图）。
 */
export function QueuePanel() {
  const store = useJobStore()
  const [dragJobId, setDragJobId] = useState<string | null>(null)
  const [confirmClear, setConfirmClear] = useState(false)
  const [clearNotice, setClearNotice] = useState<string | null>(null)

  const queued = store.queue?.queued ?? []
  const paused = store.queue?.paused ?? []
  const queueHasActivity = Boolean(store.queue?.running) || queued.length > 0

  async function handleClearStale(): Promise<void> {
    setConfirmClear(false)
    const n = await clearStaleJobs()
    setClearNotice(n > 0 ? `已清理 ${n} 个陈旧任务` : '没有需要清理的陈旧任务')
  }

  function moveBefore(sourceId: string, targetId: string): void {
    const ids = (store.queue?.queued ?? []).map((item) => item.id)
    const from = ids.indexOf(sourceId)
    const to = ids.indexOf(targetId)
    if (from < 0 || to < 0 || from === to) return
    const [moved] = ids.splice(from, 1)
    ids.splice(to, 0, moved)
    void reorderQueue(ids)
  }

  function moveToFront(jobId: string): void {
    const ids = (store.queue?.queued ?? []).map((item) => item.id)
    if (ids.indexOf(jobId) <= 0) return
    void reorderQueue([jobId, ...ids.filter((id) => id !== jobId)])
  }

  return (
    <section className="wb-queue">
      <div className="wb-queue__head">
        <div className="wb-queue__head-left">
          <h3 className="wb-queue__title">队列</h3>
          <span className="wb-queue__count" aria-label={`等待任务 ${queued.length + paused.length} 个`}>
            · {queued.length + paused.length}
          </span>
        </div>
        <div className="wb-queue__head-right">
          <ActionButton
            onClick={() => setConfirmClear(true)}
          >
            清理陈旧任务
          </ActionButton>
          {queueHasActivity && (
            store.queue?.worker.queue_paused ? (
              <ActionButton onClick={() => void resumeQueue()}>继续队列</ActionButton>
            ) : (
              <ActionButton onClick={() => void pauseQueue()}>暂停队列</ActionButton>
            )
          )}
        </div>
      </div>
      {queueHasActivity && (
        <p className="wb-queue__note">队列只调度后续任务；释放/停止后台引擎请用顶部 Power。</p>
      )}
      {clearNotice && (
        <p className="muted" role="status" data-testid="clear-stale-notice" onClick={() => setClearNotice(null)}>
          {clearNotice}
        </p>
      )}
      {store.queue?.worker.queue_paused && (
        <div className="ds-notice ds-notice--warning" role="alert">
          <p>队列已自动暂停：{store.queue.worker.queue_paused_reason ?? '系统性失败'}</p>
          <ActionButton onClick={() => void resumeQueue()}>恢复队列</ActionButton>
        </div>
      )}
      {queued.length === 0 && paused.length === 0 && <p className="muted">暂无等待任务</p>}
      {/* 紧凑队列：列表固定高度 + 内部滚动，20+ 任务不再撑高右栏；标题/暂停按钮/自动暂停提示固定在滚动区外。 */}
      <ul
        className="wb-queue-list wb-queue-list--scroll"
        style={{ maxHeight: '300px', overflowY: 'auto' }}
      >
        {queued.map((item, index) => (
          <QueueRow
            key={item.id}
            job={item}
            draggable
            dragging={dragJobId === item.id}
            onDragStart={() => setDragJobId(item.id)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={() => {
              if (dragJobId) moveBefore(dragJobId, item.id)
              setDragJobId(null)
            }}
            onDragEnd={() => setDragJobId(null)}
            actions={
              <>
                {index > 0 && (
                  <IconButton icon={<IconPrev size={14} />} label="优先" tooltip="置顶优先" onClick={() => moveToFront(item.id)} />
                )}
                <IconButton icon={<IconPause size={14} />} label="暂停" onClick={() => void pauseJob(item.id)} />
                <IconButton icon={<IconCancel size={14} />} label="取消" onClick={() => void cancelJob(item.id)} />
              </>
            }
          />
        ))}
        {paused.map((item) => (
          <QueueRow
            key={item.id}
            job={item}
            actions={
              <>
                <IconButton icon={<IconResume size={14} />} label="继续" onClick={() => void resumeJob(item.id)} />
                <IconButton icon={<IconCancel size={14} />} label="取消" onClick={() => void cancelJob(item.id)} />
              </>
            }
          />
        ))}
      </ul>
      <ConfirmModal
        open={confirmClear}
        title="清理陈旧任务？"
        message="会把上次未正常结束的排队中 / 运行中 / 已暂停任务标记为已中断，不会删除已生成的图片。"
        confirmText="清理"
        cancelText="取消"
        onConfirm={() => void handleClearStale()}
        onCancel={() => setConfirmClear(false)}
      />
    </section>
  )
}

// ===== 队列行 =====

interface QueueRowProps {
  job: JobDTO
  actions: ReactNode
  draggable?: boolean
  dragging?: boolean
  onDragStart?: () => void
  onDragOver?: (event: DragEvent) => void
  onDrop?: () => void
  onDragEnd?: () => void
}

function QueueRow({ job, actions, draggable, dragging, onDragStart, onDragOver, onDrop, onDragEnd }: QueueRowProps) {
  const excerpt = job.positive_prompt_snapshot.trim() || '（无 Prompt）'
  return (
    <li
      className={`wb-queue-item${dragging ? ' wb-queue-item--dragging' : ''}`}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
    >
      <div className="wb-queue-item__body">
        <div className="wb-queue-item__title">
          {draggable && <span className="wb-queue-item__handle" title="拖拽排序" aria-hidden="true">⋮⋮</span>}
          {job.status === 'PAUSED' && <StatusBadge status="PAUSED" />}
          <span title={excerpt}>{excerpt.length > 18 ? `${excerpt.slice(0, 18)}…` : excerpt}</span>
        </div>
        <div className="wb-queue-item__meta muted">
          {shortJobId(job.id)} · {job.requested_count} 张 ·{' '}
          {job.stages && job.stages.length > 1
            ? job.stages.map((stage) => MODULE_LABEL[stage.module_id] ?? stage.module_id).join(' + ')
            : MODULE_LABEL[job.module_id ?? ''] ?? '基础生成'}
        </div>
      </div>
      <div className="wb-queue-item__actions">{actions}</div>
    </li>
  )
}
