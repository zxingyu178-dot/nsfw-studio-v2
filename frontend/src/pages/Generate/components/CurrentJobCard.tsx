import { Button, ElapsedTimer, ProgressBar, StatusBadge } from '../../../components/ui'
import { pauseJob, resumeJob, cancelJob, resumeRemaining } from '../../../stores/jobStore'
import {
  MODULE_LABEL,
  STAGE_LABEL,
  shortJobId,
  type JobDTO,
} from '../../../types/workbench'
import { overallProgress, stageProgressLines } from '../../../utils/jobProgress'

/**
 * 当前任务卡片（规范 §五十三）：状态徽标 / Prompt 摘要 / 进度 / 分阶段 / 模块 / 耗时 / 操作。
 * 从 SettingsPane.tsx 纯拆分（Phase 0.12 任务 9：只重构，不改行为 / API）。
 */
export function CurrentJobCard({ job, busy }: { job: JobDTO; busy: boolean }) {
  const runningItem = job.items.find((item) => item.status === 'RUNNING')
  const progress = overallProgress(job)
  const stageLines = stageProgressLines(job)
  const progressText =
    job.status === 'RUNNING' && runningItem
      ? `第 ${runningItem.item_index + 1} 张 · ${progress}%`
      : `已完成 ${job.completed_count} / ${job.requested_count}`
  const moduleLabel =
    stageLines.length > 0
      ? job.stages.map((stage) => MODULE_LABEL[stage.module_id] ?? stage.module_id).join(' → ')
      : MODULE_LABEL[job.module_id ?? ''] ?? job.module_id ?? '基础生成'
  const excerpt = job.positive_prompt_snapshot.trim() || '（无 Prompt）'
  const canResumeRemaining =
    ['FAILED', 'CANCELLED', 'INTERRUPTED'].includes(job.status) &&
    job.completed_count < job.requested_count

  return (
    <section className="wb-job">
      <div className="wb-job__head">
        <StatusBadge status={job.status} />
        <span className="muted">{shortJobId(job.id)}</span>
      </div>
      <p className="wb-job__title" title={excerpt}>
        {excerpt.length > 28 ? `${excerpt.slice(0, 28)}…` : excerpt}
      </p>
      <ProgressBar value={progress / 100} ariaLabel="任务进度" />
      {stageLines.length > 0 ? (
        <ul className="wb-stages" aria-label="分阶段进度">
          {stageLines.map((line) => (
            <li key={line.key} className={line.done ? 'wb-stages__done' : undefined}>
              {line.text}
            </li>
          ))}
        </ul>
      ) : (
        <p className="wb-job__meta">
          {progressText}
          {runningItem?.current_stage ? ` · ${STAGE_LABEL[runningItem.current_stage] ?? runningItem.current_stage}` : ''}
        </p>
      )}
      <p className="wb-job__meta">{moduleLabel}</p>
      {job.started_at && (
        <p className="wb-job__meta">
          <ElapsedTimer startedAt={job.started_at} finishedAt={job.finished_at} />
        </p>
      )}
      {job.resume_of_job_id && <p className="muted">续跑自 {shortJobId(job.resume_of_job_id)}</p>}
      {job.error_message && (
        <p className="ds-notice ds-notice--error">{job.error_type}：{job.error_message}</p>
      )}

      <div className="wb-job__actions">
        {job.status === 'RUNNING' && !job.pause_requested && (
          <Button size="sm" disabled={busy} onClick={() => void pauseJob(job.id)}>暂停</Button>
        )}
        {job.status === 'RUNNING' && job.pause_requested && (
          <span className="muted">将在当前图完成后暂停…</span>
        )}
        {job.status === 'QUEUED' && (
          <Button size="sm" disabled={busy} onClick={() => void pauseJob(job.id)}>暂停</Button>
        )}
        {job.status === 'PAUSED' && (
          <Button size="sm" disabled={busy} onClick={() => void resumeJob(job.id)}>继续</Button>
        )}
        {job.status === 'RUNNING' && job.cancel_requested && <span className="muted">正在取消…</span>}
        {['QUEUED', 'RUNNING', 'PAUSED'].includes(job.status) && !job.cancel_requested && (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => void cancelJob(job.id)}>取消</Button>
        )}
        {canResumeRemaining && (
          <Button size="sm" variant="primary" disabled={busy} onClick={() => void resumeRemaining(job.id)}>
            继续剩余图片
          </Button>
        )}
      </div>
    </section>
  )
}
