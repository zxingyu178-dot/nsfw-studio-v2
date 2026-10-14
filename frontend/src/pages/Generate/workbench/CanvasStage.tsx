/**
 * CanvasStage（v0.15 Workbench 4.0 中栏，Canvas First）：
 * 由 0.14 ResultPane 升级：中心改为 Direct Canvas 视口（zoom-to-cursor / 平移 / Fit·100% / rendition 分层），
 * 顶部浮 ProgressHUD（总进度/第N张/阶段/Step/Elapsed），底部 filmstrip（thumbnail）+ ActionDock。
 * 数据逻辑沿用：activeJob + 分页拉全 Job family 图片，favorite/keep/reject 乐观更新；Lightbox 退为全屏查看。
 */
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiRequestError, imageApi } from '../../../api/client'
import { CanvasViewport } from '../../../components/CanvasViewport/CanvasViewport'
import { EmptyState, Spinner, StatusBadge } from '../../../components/ui'
import { ActionDock, IconButton, IconFavorite, IconKeep, IconReject } from '../../../components/ui/ui3'
import { ImageLightbox } from '../../../components/ImageLightbox'
import { activeJob, useJobStore } from '../../../stores/jobStore'
import {
  imageContentUrl,
  imagePreviewUrl,
  imageThumbUrl,
  shortJobId,
  type ImageDTO,
} from '../../../types/workbench'
import { ProgressHUD } from './ProgressHUD'

async function fetchAllJobImages(jobIds: string[]): Promise<ImageDTO[]> {
  const PAGE_SIZE = 100
  const merged: ImageDTO[] = []
  for (const jobId of jobIds) {
    let offset = 0
    for (let guard = 0; guard < 50; guard++) {
      const res = await imageApi.list({ job_id: jobId, limit: PAGE_SIZE, offset })
      merged.push(...res.items)
      if (res.items.length < PAGE_SIZE || offset + res.items.length >= res.total) break
      offset += res.items.length
    }
  }
  return merged
}

export function CanvasStage() {
  const store = useJobStore()
  const job = activeJob(store)
  const [images, setImages] = useState<ImageDTO[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [lightboxOpen, setLightboxOpen] = useState(false)

  const jobId = job?.id ?? null
  const parentId = job?.resume_of_job_id ?? null
  const completedCount = job?.completed_count ?? 0
  const completedStageItems = job?.stages?.reduce((total, stage) => total + stage.completed_count, 0) ?? 0

  useEffect(() => {
    if (!jobId) {
      setImages([])
      return
    }
    let cancelled = false
    const ids = parentId ? [jobId, parentId] : [jobId]
    void fetchAllJobImages(ids)
      .then((merged) => {
        if (cancelled) return
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
  const isRunning = Boolean(job && (job.status === 'RUNNING' || job.status === 'QUEUED'))

  const patchShown = useCallback(
    (patch: Partial<ImageDTO>) => {
      setImages((prev) => prev.map((image) => (image.id === shown?.id ? { ...image, ...patch } : image)))
    },
    [shown?.id],
  )

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

  const lightboxIndex = shown ? Math.max(0, images.findIndex((i) => i.id === shown.id)) : 0

  return (
    <div className="wb4-stage">
      <div className="wb4-stage__topbar">
        {job ? (
          <>
            <Link className="wb-gallery-link" to={`/gallery?job=${job.id}`}>去图库</Link>
            <span className="muted">{shortJobId(job.id)}</span>
            <StatusBadge status={job.status} />
          </>
        ) : (
          <span className="muted">Canvas</span>
        )}
      </div>

      <div className="wb4-stage__canvas">
        {isRunning && job && (
          <div className="wb4-stage__hud">
            <ProgressHUD job={job} />
          </div>
        )}

        {!job && (
          <EmptyState title="暂无生成结果" description="填写 Prompt 并点击“生成”，结果会实时显示在这里。" />
        )}

        {job && shown && (
          <CanvasViewport
            imageUrl={imagePreviewUrl(shown.id)}
            contentUrl={imageContentUrl(shown.id)}
            alt="生成结果"
            badge={shown.kind === 'upscaled' ? 'HD' : shown.kind === 'processed' ? '处理图' : undefined}
            onFullscreen={() => setLightboxOpen(true)}
          />
        )}

        {job && !shown && (
          <div className="result-stage__placeholder">
            {isRunning ? (
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

      {error && <p className="ds-notice ds-notice--error">{error}</p>}

      {/* 底部：filmstrip + 当前图动作（Canvas 主查看，filmstrip 用 thumbnail）。 */}
      {images.length > 0 && (
        <div className="wb4-stage__dock">
          <div className="result-filmstrip wb4-filmstrip" aria-label="本任务已完成图片">
            {images.map((image) => (
              <button
                key={image.id}
                type="button"
                className={`wb4-filmstrip__item${shown?.id === image.id ? ' wb4-filmstrip__item--active' : ''}`}
                aria-pressed={shown?.id === image.id}
                aria-label={`查看第 ${images.indexOf(image) + 1} 张${image.kind === 'upscaled' ? '（高清放大）' : ''}`}
                title={`${image.kind === 'upscaled' ? '高清 · ' : ''}Seed ${image.seed ?? '—'}`}
                onClick={() => setSelectedId(image.id)}
              >
                <img src={imageThumbUrl(image.id)} alt="" loading="lazy" />
                <span className="wb4-filmstrip__badge">
                  {image.kind === 'upscaled' ? 'HD' : images.indexOf(image) + 1}
                </span>
              </button>
            ))}
          </div>
          {shown && (
            <ActionDock label="图片动作">
              <IconButton
                icon={<IconFavorite size={16} />}
                label={shown.favorite ? '已收藏' : '收藏'}
                tone={shown.favorite ? 'favorite' : 'muted'}
                active={shown.favorite}
                onClick={() => void handleToggleFavorite()}
              />
              <IconButton icon={<IconKeep size={16} />} label="保留" onClick={() => void handleReview('KEEP')} />
              <IconButton icon={<IconReject size={16} />} label="淘汰" onClick={() => void handleReview('REJECT')} />
            </ActionDock>
          )}
        </div>
      )}

      {lightboxOpen && shown && (
        <ImageLightbox
          images={images}
          index={lightboxIndex}
          onClose={() => setLightboxOpen(false)}
          onNavigate={(next) => setSelectedId(images[next]?.id ?? null)}
        />
      )}
    </div>
  )
}

export default CanvasStage
