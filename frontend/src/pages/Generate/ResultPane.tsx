import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiRequestError, imageApi } from '../../api/client'
import { Badge, Button, EmptyState, ElapsedTimer, Spinner, StatusBadge } from '../../components/ui'
import { ImageLightbox } from '../../components/ImageLightbox'
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
 * 中栏（规范 §五十；Phase 0.12 任务 5.2 视觉核心）：
 * 当前生成大图舞台 + 生成中简洁状态（第 N/M · Stage · 已运行）+ 完成后动作
 * （双击放大 / 收藏 / 保留 / 淘汰 / 去图库）+ 缩略条（选中态强化）+ HD/processed 统一 Badge。
 * 图片生成完成一张立即显示一张；父子 Job（续跑，§二十）合并展示。
 */
export function ResultPane() {
  const store = useJobStore()
  const job = activeJob(store)
  const [images, setImages] = useState<ImageDTO[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Lightbox：null = 关闭；否则为当前图在 images 中的下标
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)

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
    // 分页拉全 Job family（Phase 0.12 任务 10.5：去掉硬编码 limit=200，循环到 has_next=false）
    void fetchAllJobImages(ids).then((merged) => {
      if (cancelled) return
      merged.sort((a, b) => a.created_at.localeCompare(b.created_at))
      setImages(merged)
      setError(null)
    }).catch((err: unknown) => {
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

  function openLightboxFor(image: ImageDTO): void {
    const index = images.findIndex((item) => item.id === image.id)
    if (index >= 0) setLightboxIndex(index)
  }

  /** 完成后动作：收藏 / 保留 / 淘汰——乐观更新本地当前图，不重拉整列。 */
  const patchShown = useCallback((patch: Partial<ImageDTO>) => {
    setImages((prev) => prev.map((image) => (image.id === shown?.id ? { ...image, ...patch } : image)))
  }, [shown?.id])

  async function handleToggleFavorite(): Promise<void> {
    if (!shown) return
    const next = !shown.favorite
    patchShown({ favorite: next })
    try {
      await imageApi.favorite(shown.id, next)
    } catch {
      patchShown({ favorite: !next })
    }
  }

  async function handleReview(status: 'KEEP' | 'REJECT'): Promise<void> {
    if (!shown) return
    patchShown({ status })
    try {
      await imageApi.setStatus(shown.id, { status })
    } catch {
      patchShown({ status: shown.status })
    }
  }

  return (
    <Pane title="预览" actions={job ? <StatusBadge status={job.status} /> : undefined}>
      {!job && (
        <EmptyState title="暂无生成结果" description="填写 Prompt 并点击“生成”，结果会实时显示在这里。" />
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
                ? `正在生成第 ${runningItem.item_index + 1}/${job.requested_count} 张 · ${progress}%${
                    runningItem.current_stage ? ` · ${STAGE_LABEL[runningItem.current_stage] ?? runningItem.current_stage}` : ''
                  }`
                : `已完成 ${job.completed_count} / ${job.requested_count}`}
              {job.started_at && (
                <>
                  {' · '}
                  <ElapsedTimer startedAt={job.started_at} finishedAt={job.finished_at} />
                </>
              )}
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

          <div
            className="result-stage"
            onDoubleClick={() => { if (shown) openLightboxFor(shown) }}
          >
            {shown ? (
              <>
                <img src={imageContentUrl(shown.id)} alt="生成结果" />
                {(shown.kind === 'upscaled' || shown.kind === 'processed') && (
                  <Badge tone="info" className="result-stage__hd">
                    {shown.kind === 'upscaled' ? 'HD' : '处理图'}
                  </Badge>
                )}
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

          {/* 完成后动作：双击放大 / 收藏 / 保留 / 淘汰 / 去图库 */}
          {shown && (
            <div className="wb-result-actions">
              <Button size="xs" variant="ghost" onClick={() => openLightboxFor(shown)}>放大</Button>
              <Button
                size="xs"
                variant={shown.favorite ? 'secondary' : 'ghost'}
                onClick={() => void handleToggleFavorite()}
              >
                {shown.favorite ? '已收藏 ★' : '收藏'}
              </Button>
              <Button size="xs" variant="ghost" onClick={() => void handleReview('KEEP')}>保留</Button>
              <Button size="xs" variant="ghost" onClick={() => void handleReview('REJECT')}>淘汰</Button>
              <Link className="ds-btn ds-btn--ghost ds-btn--sm" to={`/gallery?job=${job.id}`}>
                去图库
              </Link>
            </div>
          )}

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
                  onDoubleClick={() => openLightboxFor(image)}
                  title={`${image.kind === 'upscaled' ? '高清 · ' : ''}Seed ${image.seed ?? '—'}`}
                >
                  <img src={imageContentUrl(image.id)} alt="" loading="lazy" />
                  {(image.kind === 'upscaled' || image.kind === 'processed') && (
                    <Badge tone="info" className="wb-thumbs__hd">
                      {image.kind === 'upscaled' ? 'HD' : '处理'}
                    </Badge>
                  )}
                </button>
              ))}
            </div>
          )}
        </>
      )}

      {error && <p className="ds-notice ds-notice--error">{error}</p>}

      {lightboxIndex !== null && (
        <ImageLightbox
          images={images}
          index={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onNavigate={(next) => setLightboxIndex(next)}
        />
      )}
    </Pane>
  )
}

export default ResultPane

/**
 * 分页拉全一个或多个 Job family 的图片（Phase 0.12 任务 10.5）。
 * 旧实现硬编码 limit=200；这里按 limit/offset 逐页拉满到 total，契约上不再有隐形上限。
 * 共享 ListResponse 冻结形状为 { items, total, limit, offset }（无 has_next），
 * 故用“整页未读完或累计 < total”判定是否继续翻页。
 */
async function fetchAllJobImages(jobIds: string[]): Promise<ImageDTO[]> {
  const PAGE_SIZE = 100
  const merged: ImageDTO[] = []
  for (const jobId of jobIds) {
    let offset = 0
    // 安全阀：Job 图片即便异常膨胀也不会无限翻页（正常单 Job 产物远小于此）
    for (let guard = 0; guard < 50; guard++) {
      const res = await imageApi.list({ job_id: jobId, limit: PAGE_SIZE, offset })
      merged.push(...res.items)
      if (res.items.length < PAGE_SIZE || offset + res.items.length >= res.total) break
      offset += res.items.length
    }
  }
  return merged
}
