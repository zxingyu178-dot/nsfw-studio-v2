import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiRequestError, imageApi } from '../../api/client'
import { EmptyState, Spinner, StatusBadge } from '../../components/ui'
import { activeJob, useJobStore } from '../../stores/jobStore'
import {
  STAGE_LABEL,
  imageContentUrl,
  shortJobId,
  type ImageDTO,
} from '../../types/workbench'
import { overallProgress, stageProgressLines } from '../../utils/jobProgress'
import { Pane } from './Pane'

/**
 * 中栏（规范 §五十）：当前生成图片 + 本 Job 已完成缩略图。
 * 图片生成完成一张立即显示一张；父子 Job（续跑，§二十）合并展示。
 */
export function ResultPane() {
  const store = useJobStore()
  const job = activeJob(store)
  const [images, setImages] = useState<ImageDTO[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const jobId = job?.id ?? null
  const parentId = job?.resume_of_job_id ?? null
  const completedCount = job?.completed_count ?? 0
  // §十八：Stage 每完成一张立即刷新缩略图（多阶段下 completed_count 只在最后 Stage 增长）
  const completedStageItems =
    job?.stages?.reduce((total, stage) => total + stage.completed_count, 0) ?? 0

  useEffect(() => {
    if (!jobId) {
      setImages([])
      return
    }
    let cancelled = false
    const ids = parentId ? [jobId, parentId] : [jobId]
    Promise.all(ids.map((id) => imageApi.list({ job_id: id, limit: 200 })))
      .then((pages) => {
        if (cancelled) return
        const merged = pages.flatMap((page) => page.items)
        merged.sort((a, b) => a.created_at.localeCompare(b.created_at))
        setImages(merged)
        setError(null)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : '无法加载图片')
      })
    return () => {
      cancelled = true
    }
  }, [jobId, parentId, completedCount, completedStageItems])

  useEffect(() => {
    setSelectedId(null)
  }, [jobId])

  const shown = images.find((image) => image.id === selectedId) ?? images[images.length - 1] ?? null
  const runningItem = job?.items.find((item) => item.status === 'RUNNING') ?? null
  const progress = job ? overallProgress(job) : 0
  const stageLines = job ? stageProgressLines(job) : []

  return (
    <Pane title="预览" actions={job ? <StatusBadge status={job.status} /> : undefined}>
      {!job && (
        <EmptyState
          title="暂无生成结果"
          description="填写 Prompt 并点击“生成”，结果与缩略图会实时显示在这里。"
        />
      )}

      {job && (
        <>
          <p className="muted wb-jobline">
            {shortJobId(job.id)}
            {job.resume_of_job_id ? `（续跑自 ${shortJobId(job.resume_of_job_id)}）` : ''}
            {' · '}
            {stageLines.length > 0
              ? `原图生成 + 高清放大 · 已完成 ${job.completed_count} / ${job.requested_count}`
              : job.status === 'RUNNING' && runningItem
                ? `正在生成第 ${runningItem.item_index + 1} 张 · ${progress}%${
                    runningItem.current_stage ? ` · ${STAGE_LABEL[runningItem.current_stage] ?? runningItem.current_stage}` : ''
                  }`
                : `已完成 ${job.completed_count} / ${job.requested_count}`}
          </p>

          {stageLines.length > 0 && (
            <ul className="wb-stages" aria-label="分阶段进度">
              {stageLines.map((line) => (
                <li key={line.key} className={line.done ? 'wb-stages__done' : undefined}>
                  {line.text}
                </li>
              ))}
            </ul>
          )}

          <div className="result-stage">
            {shown ? (
              <>
                <img src={imageContentUrl(shown.id)} alt="生成结果" />
                {shown.kind === 'upscaled' && <span className="result-stage__hd">HD</span>}
              </>
            ) : (
              <div className="result-stage__placeholder">
                {job.status === 'RUNNING' || job.status === 'QUEUED' ? (
                  <>
                    <Spinner ariaLabel="正在生成" />
                    <p className="muted">正在生成，完成后逐张显示…</p>
                  </>
                ) : (
                  <p className="muted">本任务暂无图片</p>
                )}
              </div>
            )}
          </div>

          {images.length > 0 && (
            <div className="wb-thumbs" role="list" aria-label="本任务已完成图片">
              {images.map((image) => (
                <button
                  key={image.id}
                  type="button"
                  role="listitem"
                  className={`wb-thumbs__item${
                    shown?.id === image.id ? ' wb-thumbs__item--active' : ''
                  }`}
                  onClick={() => setSelectedId(image.id)}
                  title={`${image.kind === 'upscaled' ? '高清 · ' : ''}Seed ${image.seed ?? '—'}`}
                >
                  <img src={imageContentUrl(image.id)} alt="" loading="lazy" />
                  {image.kind === 'upscaled' && <span className="wb-thumbs__hd">HD</span>}
                </button>
              ))}
            </div>
          )}

          <Link className="ds-btn ds-btn--ghost ds-btn--sm" to={`/gallery?job=${job.id}`}>
            在图库中查看本任务
          </Link>
        </>
      )}

      {error && <p className="ds-notice ds-notice--error">{error}</p>}
      <p className="muted">
        图片来源于真实引擎输出，已导入 Studio 数据目录；全部完成后可在图库审核、保留或淘汰。
      </p>
    </Pane>
  )
}

export default ResultPane
