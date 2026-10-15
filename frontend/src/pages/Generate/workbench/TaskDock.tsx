/**
 * TaskDock（v0.15 Task 12）：底部任务坞。
 * 收起态（36–40px）：●状态 · 第N/M · 总进度 · 队列数 · 展开 · 暂停后续（tooltip 明确只暂停调度）。
 * 展开态：Current Job（去掉进度条/Stage/elapsed/第N张——这些已在 Canvas HUD）+ 队列全部能力（QueuePanel 原样复用）。
 */
import { Button, StatusBadge, Tooltip } from '../../../components/ui'
import { IconButton, IconChevronDown, IconPause, IconResume } from '../../../components/ui/ui3'
import { cancelJob, pauseJob, pauseQueue, resumeJob, resumeQueue, useJobStore } from '../../../stores/jobStore'
import { MODULE_LABEL, shortJobId, type JobDTO } from '../../../types/workbench'
import { QueuePanel } from '../components/QueuePanel'
import { hudSnapshot } from './workbenchProgress'
import { toggleDock, useWorkbenchLayout } from './workbenchLayout'

export function TaskDock() {
  const store = useJobStore()
  const open = useWorkbenchLayout().dockOpen
  const live = store.liveProgressByStageItem
  const running = store.queue?.running ?? null
  const queuedCount = (store.queue?.queued ?? []).length + (store.queue?.paused ?? []).length
  const paused = store.queue?.worker.queue_paused ?? false

  const hud = running ? hudSnapshot(running, live) : null
  // v0.15.1：动作忙态必须绑定到具体 job（busyJobId），而非全局 submitting；
  // 只对当前 dock 展示的那个 running job 置忙，避免别的任务操作时误禁用。
  const busy = store.submitting || (running !== null && store.busyJobId === running.id)
  const busyAction = store.busyJobId === running?.id ? store.busyJobAction : null

  return (
    <div className={`wb4-dock glass${open ? ' wb4-dock--open' : ''}`} data-testid="task-dock">
      {/* 收起态条（常驻 36–40px） */}
      <div className="wb4-dock__bar">
        <button type="button" className="wb4-dock__expand" onClick={() => toggleDock()} aria-expanded={open}>
          <IconChevronDown size={14} className={open ? 'wb4-dock__chevron wb4-dock__chevron--up' : 'wb4-dock__chevron'} />
          <span className="wb4-dock__title">任务</span>
        </button>

        {running ? (
          <div className="wb4-dock__status">
            <span className="wb4-dock__dot wb4-dock__dot--run" aria-hidden="true" />
            <span className="wb4-dock__label">{running.status === 'RUNNING' ? 'RUNNING' : 'QUEUED'}</span>
            {hud?.currentItem != null && hud.itemTotal != null && (
              <span className="wb4-dock__item">第 {hud.currentItem}/{hud.itemTotal} 张</span>
            )}
            <span className="wb4-dock__overall">{hud?.overall ?? 0}%</span>
          </div>
        ) : (
          <div className="wb4-dock__status">
            <span className="wb4-dock__dot" aria-hidden="true" />
            <span className="wb4-dock__label">空闲</span>
          </div>
        )}

        <span className="wb4-dock__queue-count" aria-label={`等待任务 ${queuedCount} 个`}>
          队列 {queuedCount}
        </span>

        <div className="wb4-dock__bar-actions">
          <Tooltip content="只暂停任务调度，不停止 Python/ComfyUI 引擎（释放/停止引擎请用顶部 Power）" side="top">
            {paused ? (
              <IconButton icon={<IconResume size={14} />} label="继续后续任务" onClick={() => void resumeQueue()} />
            ) : (
              <IconButton icon={<IconPause size={14} />} label="暂停后续任务" onClick={() => void pauseQueue()} />
            )}
          </Tooltip>
        </div>
      </div>

      {/* 展开态：当前任务（无进度细节）+ 队列全能力 */}
      {open && (
        <div className="wb4-dock__body">
          <div className="wb4-dock__current">
            {running ? (
              <CompactCurrentJob job={running} busy={busy} busyAction={busyAction} />
            ) : (
              <p className="muted">当前没有运行中的任务。</p>
            )}
          </div>
          <div className="wb4-dock__queue">
            <QueuePanel />
          </div>
        </div>
      )}
    </div>
  )
}

/** 展开态当前任务：保留状态/摘要/模块/操作，去掉进度条/Stage/elapsed/第N张（已在 Canvas HUD）。 */
function CompactCurrentJob({
  job,
  busy,
  busyAction,
}: {
  job: JobDTO
  busy: boolean
  busyAction: 'pause' | 'resume' | 'cancel' | null
}) {
  const excerpt = (job.positive_prompt_snapshot ?? '').trim() || '（无 Prompt）'
  const moduleLabel =
    job.stages && job.stages.length > 1
      ? job.stages.map((stage) => MODULE_LABEL[stage.module_id] ?? stage.module_id).join(' → ')
      : MODULE_LABEL[job.module_id ?? ''] ?? '基础生成'
  return (
    <section className="wb-job wb4-dock__job">
      <div className="wb-job__head">
        <StatusBadge status={job.status} />
        <span className="muted">{shortJobId(job.id)}</span>
        <span className="muted">{moduleLabel}</span>
      </div>
      <p className="wb-job__title" title={excerpt}>
        {excerpt.length > 32 ? `${excerpt.slice(0, 32)}…` : excerpt}
      </p>
      <div className="wb-job__actions">
        {job.status === 'RUNNING' && !job.pause_requested && (
          <Button size="sm" disabled={busy} aria-busy={busyAction === 'pause'}
                  onClick={() => void pauseJob(job.id)}>
            {busyAction === 'pause' ? '正在暂停…' : '暂停'}
          </Button>
        )}
        {job.status === 'PAUSED' && (
          <Button size="sm" disabled={busy} aria-busy={busyAction === 'resume'}
                  onClick={() => void resumeJob(job.id)}>
            {busyAction === 'resume' ? '正在继续…' : '继续'}
          </Button>
        )}
        {['QUEUED', 'RUNNING', 'PAUSED'].includes(job.status) && !job.cancel_requested && (
          <Button size="sm" variant="ghost" disabled={busy} aria-busy={busyAction === 'cancel'}
                  onClick={() => void cancelJob(job.id)}>
            {busyAction === 'cancel' ? '正在取消…' : '取消'}
          </Button>
        )}
        {job.status === 'RUNNING' && job.cancel_requested && <span className="muted">正在取消…</span>}
      </div>
    </section>
  )
}

export default TaskDock
