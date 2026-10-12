// 多阶段进度展示（Phase 3 §十七/§十八）：原图生成 / 高清放大 各自一行，用户一眼知道当前处于哪个阶段。
import { MODULE_LABEL, type JobDTO, type JobStageDTO } from '../types/workbench'

export interface StageProgressLine {
  key: string
  text: string
  done: boolean
}

function stageLine(stage: JobStageDTO): StageProgressLine {
  const label = MODULE_LABEL[stage.module_id] ?? stage.module_id
  const base = `${label} ${stage.completed_count} / ${stage.total_count}`
  if (stage.status === 'COMPLETED') return { key: stage.id, text: `${base} ✓`, done: true }
  if (stage.status === 'FAILED') return { key: stage.id, text: `${base} · 失败`, done: false }
  if (stage.status === 'CANCELLED') return { key: stage.id, text: `${base} · 已取消`, done: false }
  const running = stage.items.find((item) => item.status === 'RUNNING')
  if (running) {
    const percent = Math.round((running.progress ?? 0) * 100)
    return {
      key: stage.id,
      text: `${base} · 第 ${running.item_index + 1} 张 · ${percent}%`,
      done: false,
    }
  }
  return { key: stage.id, text: base, done: false }
}

/** 分阶段进度行（单模块 Job 返回空数组，由调用方退回旧文案） */
export function stageProgressLines(job: JobDTO): StageProgressLine[] {
  if (!job.stages || job.stages.length < 2) return []
  return job.stages.map(stageLine)
}

/** 进度条百分比：优先当前 Stage 进度，否则最终完成比例 */
export function overallProgress(job: JobDTO): number {
  const runningStage = job.stages?.find((stage) => stage.status === 'RUNNING')
  if (runningStage && runningStage.progress != null) {
    return Math.round(runningStage.progress * 100)
  }
  const runningItem = job.items.find((item) => item.status === 'RUNNING')
  if (runningItem?.progress != null) return Math.round(runningItem.progress * 100)
  return job.requested_count > 0 ? Math.round((job.completed_count / job.requested_count) * 100) : 0
}

/** v0.13.2：失败原因的可读中文文案。
 *  ENGINE_STALLED（引擎 stall_timeout 内 progress 一直 0，已自动判失败并释放队列头）翻成人话，
 *  不再把机器码直接甩给用户；其余错误保留"类型：详情"。 */
export function jobErrorText(errorType: string | null, errorMessage: string | null): string | null {
  if (!errorType && !errorMessage) return null
  if (errorType === 'ENGINE_STALLED') {
    return '引擎长时间无进度，已自动停止并释放队列头，可重试该任务。'
  }
  return `${errorType ?? '失败'}：${errorMessage ?? ''}`
}