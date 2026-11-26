/**
 * ProgressHUD（v0.15 Task 9/13）：Canvas 顶部轻量毛玻璃，集中展示生成进度。
 * - 总进度：跨全部 Stage 工作单元加权（workOverall），不用当前 stage 冒充；
 * - 第 N/M 张；阶段 x/y · 名称；
 * - Step x/y · pct% 仅在真实采样 step 有值时显示；非采样阶段显示“处理中…”，绝不伪造；
 * - Elapsed 仅在此处显示（CurrentJobCard 不再重复）。
 * v0.37.6：QUEUED 也显示进度 HUD（0% + 排队位次），终态显示完成/失败/取消，避免“看不到进度”。
 */
import { ElapsedTimer } from '../../../components/ui/ElapsedTimer'
import { useJobStore } from '../../../stores/jobStore'
import type { JobDTO } from '../../../types/workbench'
import { hudSnapshot } from './workbenchProgress'

export interface ProgressHUDProps {
  job: JobDTO
  /** QUEUED 时在前方等待的任务数。 */
  queueAhead?: number
  /** 当前真正运行的任务 id（用于切走查看）。 */
  runningJobId?: string | null
  onTrackRunning?: () => void
}

const STATUS_LABEL: Partial<Record<JobDTO['status'], string>> = {
  COMPLETED: '已完成',
  FAILED: '生成失败',
  CANCELLED: '已取消',
  INTERRUPTED: '已中断',
  PAUSED: '已暂停',
}

export function ProgressHUD({ job, queueAhead = 0, runningJobId, onTrackRunning }: ProgressHUDProps) {
  const live = useJobStore().liveProgressByStageItem
  const hud = hudSnapshot(job, live)
  const isQueued = job.status === 'QUEUED'
  const terminalLabel = STATUS_LABEL[job.status]
  const overall = isQueued ? 0 : hud.overall

  const showStep = hud.step !== null && hud.maxStep !== null && hud.maxStep > 0
  const stepPct = showStep ? Math.round(((hud.step ?? 0) / (hud.maxStep ?? 1)) * 100) : 0

  return (
    <div className="wb4-hud glass" role="status" aria-label="生成进度" data-testid="progress-hud">
      <div className="wb4-hud__row">
        <div className="wb4-hud__progress">
          <div className="wb4-hud__bar">
            <div className="wb4-hud__bar-fill" style={{ width: `${overall}%` }} />
          </div>
          <span className="wb4-hud__overall">{isQueued ? '排队中' : `${overall}%`}</span>
        </div>
        {job.status === 'RUNNING' && hud.startedAt && <ElapsedTimer startedAt={hud.startedAt} label="已运行" />}
      </div>

      {isQueued ? (
        <div className="wb4-hud__meta">
          <span className="wb4-hud__item">
            已加入队列 · 前方 {queueAhead} 个任务 · 等待开始
          </span>
          {runningJobId && runningJobId !== job.id && onTrackRunning && (
            <button type="button" className="ds-link" onClick={onTrackRunning}>
              查看当前运行任务
            </button>
          )}
        </div>
      ) : (
        <div className="wb4-hud__meta">
          {terminalLabel && (
            <span className={`wb4-hud__status wb4-hud__status--${job.status.toLowerCase()}`}>
              {terminalLabel}
            </span>
          )}
          {hud.currentItem !== null && hud.itemTotal !== null && (
            <span className="wb4-hud__item">第 {hud.currentItem} / {hud.itemTotal} 张</span>
          )}
          {hud.stageIndex !== null && (
            <span className="wb4-hud__stage">
              阶段 {hud.stageIndex}/{hud.stageCount} · {hud.stageLabel}
            </span>
          )}
          {showStep ? (
            <span className="wb4-hud__step">
              Step {hud.step}/{hud.maxStep} · {stepPct}%
            </span>
          ) : (
            hud.indeterminate && <span className="wb4-hud__step wb4-hud__step--indeterminate">处理中…</span>
          )}
        </div>
      )}
    </div>
  )
}

export default ProgressHUD
