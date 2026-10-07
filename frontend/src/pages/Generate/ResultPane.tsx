import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiRequestError, imageApi } from '../../api/client'
import { activeJob, useJobStore } from '../../stores/jobStore'
import {
  JOB_STATUS_LABEL,
  STAGE_LABEL,
  imageContentUrl,
  shortJobId,
  type ImageDTO,
} from '../../types/workbench'

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
  }, [jobId, parentId, completedCount])

  useEffect(() => {
    setSelectedId(null)
  }, [jobId])

  const shown = images.find((image) => image.id === selectedId) ?? images[images.length - 1] ?? null
  const runningItem = job?.items.find((item) => item.status === 'RUNNING') ?? null
  const progress =
    runningItem?.progress != null
      ? Math.round(runningItem.progress * 100)
      : job && job.requested_count > 0
        ? Math.round((job.completed_count / job.requested_count) * 100)
        : 0

  return (
    <div className="pane pane--center">
      <header className="pane__header">
        <h2 className="pane__title">预览</h2>
        {job && (
          <span className={`status-chip status-chip--${job.status.toLowerCase()}`}>
            {JOB_STATUS_LABEL[job.status]}
          </span>
        )}
      </header>

      {!job && (
        <div className="result-placeholder">
          <div className="empty-state__badge">Ready</div>
          <p className="result-placeholder__text">暂无生成结果</p>
          <p className="muted">填写 Prompt 并点击"生成"，结果与缩略图会实时显示在这里。</p>
        </div>
      )}

      {job && (
        <>
          <p className="muted result-pane__jobline">
            {shortJobId(job.id)}
            {job.resume_of_job_id ? `（续跑自 ${shortJobId(job.resume_of_job_id)}）` : ''}
            {' · '}
            {job.status === 'RUNNING' && runningItem
              ? `正在生成第 ${runningItem.item_index + 1} 张 · ${progress}%${
                  runningItem.current_stage ? ` · ${STAGE_LABEL[runningItem.current_stage] ?? runningItem.current_stage}` : ''
                }`
              : `已完成 ${job.completed_count} / ${job.requested_count}`}
          </p>

          <div className="result-pane__stage">
            {shown ? (
              <img src={imageContentUrl(shown.id)} alt="生成结果" />
            ) : (
              <div className="result-placeholder result-placeholder--inner">
                <div className="empty-state__badge">
                  {job.status === 'RUNNING' ? 'Generating' : job.status.toLowerCase()}
                </div>
                <p className="result-placeholder__text">
                  {job.status === 'RUNNING' || job.status === 'QUEUED'
                    ? '正在生成，完成后逐张显示…'
                    : '本任务暂无图片'}
                </p>
              </div>
            )}
          </div>

          {images.length > 0 && (
            <div className="thumb-strip" role="list" aria-label="本任务已完成图片">
              {images.map((image) => (
                <button
                  key={image.id}
                  type="button"
                  role="listitem"
                  className={`thumb-strip__item${
                    shown?.id === image.id ? ' thumb-strip__item--active' : ''
                  }`}
                  onClick={() => setSelectedId(image.id)}
                  title={`Seed ${image.seed ?? '—'}`}
                >
                  <img src={imageContentUrl(image.id)} alt="" loading="lazy" />
                </button>
              ))}
            </div>
          )}

          <div className="result-pane__footer">
            <Link className="btn btn--ghost btn--sm" to={`/gallery?job=${job.id}`}>
              在图库中查看本任务
            </Link>
          </div>
        </>
      )}

      {error && <p className="notice notice--error">{error}</p>}
      <p className="muted result-pane__hint">
        图片来源于真实引擎输出，已导入 Studio 数据目录；全部完成后可在图库审核、保留或淘汰。
      </p>
    </div>
  )
}