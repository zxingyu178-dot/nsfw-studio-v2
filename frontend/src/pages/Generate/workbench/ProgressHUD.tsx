/**
 * ProgressHUD（v0.15 Task 9/13）：Canvas 顶部轻量毛玻璃，集中展示生成进度。
 * - 总进度：跨全部 Stage 工作单元加权（workOverall），不用当前 stage 冒充；
 * - 第 N/M 张；阶段 x/y · 名称；
 * - Step x/y · pct% 仅在真实采样 step 有值时显示；upscale/非采样阶段显示“处理中…”，绝不伪造；
 * - Elapsed 仅在此处显示（CurrentJobCard 不再重复）。
 */
import { ElapsedTimer } from '../../../components/ui/ElapsedTimer'
import { useJobStore } from '../../../stores/jobStore'
import type { JobDTO } from '../../../types/workbench'
import { hudSnapshot } from './workbenchProgress'

export function ProgressHUD({ job }: { job: JobDTO }) {
  const live = useJobStore().liveProgressByStageItem
  const hud = hudSnapshot(job, live)

  const showStep = hud.step !== null && hud.maxStep !== null && hud.maxStep > 0
  const stepPct = showStep ? Math.round(((hud.step ?? 0) / (hud.maxStep ?? 1)) * 100) : 0

  return (
    <div className="wb4-hud glass" role="status" aria-label="生成进度" data-testid="progress-hud">
      <div className="wb4-hud__row">
        <div className="wb4-hud__progress">
          <div className="wb4-hud__bar">
            <div className="wb4-hud__bar-fill" style={{ width: `${hud.overall}%` }} />
          </div>
          <span className="wb4-hud__overall">{hud.overall}%</span>
        </div>
        {hud.startedAt && <ElapsedTimer startedAt={hud.startedAt} label="已运行" />}
      </div>
      <div className="wb4-hud__meta">
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
    </div>
  )
}

export default ProgressHUD
