/**
 * Canvas 进度 HUD 计算（v0.15 Task 9/13）：
 * 持久 JobDTO 为事实源，实时 step/progress 来自 jobStore 的 liveProgressByStageItem（按 stage_item_id）瞬态层。
 * 关键：总进度按全部 Stage 的工作单元加权，不能用“当前 running stage progress”冒充整个 Job。
 */
import { MODULE_LABEL, type JobDTO, type JobStageItemDTO } from '../../../types/workbench'
import type { LiveProgress } from '../../../stores/jobStore'

export interface HudSnapshot {
  /** 整个 Job 总进度 0–100（跨所有 Stage 工作单元加权）。 */
  overall: number
  /** 当前图片序号（1 起）与该 Stage 总张数（第 N / M 张）。 */
  currentItem: number | null
  itemTotal: number | null
  /** 阶段序号（1 起）、阶段总数、阶段中文名。 */
  stageIndex: number | null
  stageCount: number
  stageLabel: string | null
  /** 真实采样步数；仅采样型工作流有值，upscale 等阶段必须为 null。 */
  step: number | null
  maxStep: number | null
  /** 非采样阶段（如 upscale）：显示“处理中…”，绝不伪造 Step。 */
  indeterminate: boolean
  startedAt: string | null
}

const UPSCALE_MODULES = new Set(['upscale'])

/**
 * 跨 Stage 工作单元总进度：total=Σ stage.total_count，done=Σ(completed + 当前 running item 进度)。
 * v0.15.1：实时进度按 **stage_item_id**（StageItem.id）索引，多阶段同一 job_item_id 不再串进度。
 */
export function workOverall(job: JobDTO, liveByStageItem: Record<string, LiveProgress>): number {
  const stages = job.stages ?? []
  if (stages.length === 0) {
    return job.requested_count > 0 ? Math.round((job.completed_count / job.requested_count) * 100) : 0
  }
  let total = 0
  let done = 0
  for (const stage of stages) {
    total += stage.total_count
    done += stage.completed_count
    const running = stage.items.find((item) => item.status === 'RUNNING')
    if (running) {
      const live = liveByStageItem[running.id]
      const progress = live?.progress ?? running.progress ?? 0
      done += Math.max(0, Math.min(1, progress))
    }
  }
  if (total <= 0) return 0
  return Math.max(0, Math.min(100, Math.round((done / total) * 100)))
}

function liveForStageItem(
  item: JobStageItemDTO | undefined,
  liveByStageItem: Record<string, LiveProgress>,
): LiveProgress | null {
  if (!item) return null
  return liveByStageItem[item.id] ?? null
}

export function hudSnapshot(job: JobDTO, liveByStageItem: Record<string, LiveProgress> = {}): HudSnapshot {
  const stages = job.stages ?? []
  const stageCount = stages.length
  const runningStage = stages.find((s) => s.status === 'RUNNING') ?? null
  const runningItem = runningStage?.items.find((i) => i.status === 'RUNNING') ?? null
  const live = liveForStageItem(runningItem ?? undefined, liveByStageItem)

  let stageIndex: number | null = null
  let stageLabel: string | null = null
  if (runningStage) {
    stageIndex = runningStage.stage_index + 1
    stageLabel = MODULE_LABEL[runningStage.module_id] ?? runningStage.module_id
  }

  // 实时 step 优先；缺失则 null（不伪造）。
  const step = live?.step ?? null
  const maxStep = live?.maxStep ?? null
  const isUpscale = runningStage ? UPSCALE_MODULES.has(runningStage.module_id) : false
  // 非采样阶段（upscale，或引擎明确不给 step）→ 处理中
  const indeterminate = Boolean(runningStage) && (step === null || maxStep === null || maxStep <= 0)

  return {
    overall: workOverall(job, liveByStageItem),
    currentItem: runningItem ? runningItem.item_index + 1 : runningStage?.current_item != null ? runningStage.current_item + 1 : null,
    itemTotal: runningStage?.total_count ?? job.requested_count ?? null,
    stageIndex,
    stageCount,
    stageLabel: isUpscale ? '高清放大' : stageLabel,
    step,
    maxStep,
    indeterminate: isUpscale ? true : indeterminate,
    startedAt: job.started_at,
  }
}
