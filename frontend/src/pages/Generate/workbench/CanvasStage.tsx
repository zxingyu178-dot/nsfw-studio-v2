/**
 * CanvasStage（v0.15 Workbench 4.0 中栏，Canvas First）：
 * 由 0.14 ResultPane 升级：中心改为 Direct Canvas 视口（zoom-to-cursor / 平移 / Fit·100% / rendition 分层），
 * 顶部浮 ProgressHUD（总进度/第N张/阶段/Step/Elapsed），底部 filmstrip（thumbnail）+ ActionDock。
 * 数据逻辑沿用：activeJob + 分页拉全 Job family 图片，favorite/keep/reject 乐观更新；Lightbox 退为全屏查看。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiRequestError, imageApi, jobApi } from '../../../api/client'
import { CanvasViewport } from '../../../components/CanvasViewport/CanvasViewport'
import { EmptyState, Spinner, StatusBadge } from '../../../components/ui'
import { ActionDock, IconButton, IconFavorite, IconKeep, IconReject } from '../../../components/ui/ui3'
import { ImageLightbox } from '../../../components/ImageLightbox'
import { activeJob, trackJob, useJobStore } from '../../../stores/jobStore'
import {
  imageContentUrl,
  imagePreviewUrl,
  imageThumbUrl,
  shortJobId,
  type ImageDTO,
} from '../../../types/workbench'
import { ImageMutationQueue, type ImageMutation } from './imageMutationQueue'
import { ProgressHUD } from './ProgressHUD'
import { fetchResumeFamilyJobIds } from './resumeFamily'

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
  const [notice, setNotice] = useState<string | null>(null)
  const [actionPendingId, setActionPendingId] = useState<string | null>(null)
  const [lightboxOpen, setLightboxOpen] = useState(false)

  // 以服务器返回为准更新单张图片（收藏/审核成功后用响应 DTO 校正本地态）。
  const patchImageFromDto = useCallback((dto: ImageDTO) => {
    setImages((prev) => prev.map((img) =>
      img.id === dto.id ? { ...img, favorite: dto.favorite, status: dto.status } : img,
    ))
  }, [])

  // 真正落地一次变更：调 API；失败时重新 GET 权威状态校正并给出可见提示（绝不静默吞错）。
  const applyMutation = useCallback(async (imageId: string, mutation: ImageMutation): Promise<void> => {
    try {
      let dto: ImageDTO | null = null
      if (mutation.favorite !== undefined) {
        dto = await imageApi.favorite(imageId, mutation.favorite)
      }
      if (mutation.status !== undefined) {
        dto = await imageApi.setStatus(imageId, { status: mutation.status })
      }
      if (dto) patchImageFromDto(dto)
    } catch {
      try {
        const authoritative = await imageApi.get(imageId)
        patchImageFromDto(authoritative)
      } catch {
        // 重新获取也失败：保留提示，由用户在下次刷新时回源收敛
      }
      setNotice('图片状态更新失败，已恢复为服务器当前状态，请重试。')
    }
  }, [patchImageFromDto])

  // v0.15.1：每张图串行 + 最后意图合并（连点 KEEP→REJECT、反复收藏，最终恒等于最后一次点击）。
  const mutationQueueRef = useRef<ImageMutationQueue | null>(null)
  if (mutationQueueRef.current === null) {
    mutationQueueRef.current = new ImageMutationQueue(applyMutation)
  }

  const enqueueMutation = useCallback((imageId: string, mutation: ImageMutation) => {
    setActionPendingId(imageId)
    void mutationQueueRef.current!.enqueue(imageId, mutation).finally(() => {
      setActionPendingId((current) => (current === imageId ? null : current))
    })
  }, [])

  const jobId = job?.id ?? null
  const completedCount = job?.completed_count ?? 0
  const completedStageItems = job?.stages?.reduce((total, stage) => total + stage.completed_count, 0) ?? 0

  // v0.15.1：增量刷新去重——记录已加载图片的 id 集合签名（仅 id，不含 favorite/status 本地态），
  // 家族重拉后 id 集合未变（无新图）就跳过 setImages，避免每完成一张全量回源造成的重复渲染/抖动。
  const imagesKeyRef = useRef<{ jobId: string | null; key: string }>({ jobId: null, key: '' })

  useEffect(() => {
    if (!jobId) {
      setImages([])
      imagesKeyRef.current = { jobId: null, key: '' }
      return
    }
    if (imagesKeyRef.current.jobId !== jobId) {
      imagesKeyRef.current = { jobId, key: '' }
    }
    let cancelled = false
    void (async () => {
      // v0.15.1：沿 resume_of_job_id 取完整 root→current 链（A→B→C），合并全部家族图片；
      // 不再只取一层 parent，避免漏掉 root 的图片。
      const ids = await fetchResumeFamilyJobIds((id) => jobApi.get(id), jobId)
      return fetchAllJobImages(ids)
    })()
      .then((merged) => {
        if (cancelled || !merged) return
        // 按 image id 去重（resume family 各 job 理论不重叠，防御性去重）。
        const byId = new Map<string, ImageDTO>()
        for (const img of merged) byId.set(img.id, img)
        const deduped = Array.from(byId.values())
        // 仅在 id 集合真变化（新图完成/数量变化）时才重排并刷新。
        const nextKey = Array.from(byId.keys()).sort().join('|')
        if (imagesKeyRef.current.jobId === jobId && imagesKeyRef.current.key === nextKey) return
        imagesKeyRef.current = { jobId, key: nextKey }
        deduped.sort((a, b) => a.created_at.localeCompare(b.created_at))
        setImages(deduped)
        setError(null)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : '无法加载图片')
      })
    return () => {
      cancelled = true
    }
  }, [jobId, completedCount, completedStageItems])

  useEffect(() => {
    setSelectedId(null)
  }, [jobId])

  const shown = images.find((image) => image.id === selectedId) ?? images[images.length - 1] ?? null
  // v0.15.1：QUEUED 与 RUNNING 显式分离。只有 RUNNING 才显示采样 Step/Stage/Elapsed HUD；
  // QUEUED 仅表示“已排队、等待调度”，不能再误报“正在生成”。
  const isRunning = Boolean(job && job.status === 'RUNNING')
  const isQueued = Boolean(job && job.status === 'QUEUED')
  // 前方排队任务数（在 queue.queued 中的位置）；找不到时按队列长度兜底。
  const queueAhead = (() => {
    if (!isQueued || !job) return 0
    const queued = store.queue?.queued ?? []
    const idx = queued.findIndex((q) => q.id === job.id)
    return idx >= 0 ? idx : queued.length
  })()
  const currentRunningId = store.queue?.running?.id ?? null

  const patchShown = useCallback(
    (patch: Partial<ImageDTO>) => {
      setImages((prev) => prev.map((image) => (image.id === shown?.id ? { ...image, ...patch } : image)))
    },
    [shown?.id],
  )

  function handleToggleFavorite(): void {
    if (!shown) return
    const next = !shown.favorite
    patchShown({ favorite: next }) // 乐观即时反馈
    enqueueMutation(shown.id, { favorite: next }) // 串行落地 + 最后意图合并
  }

  function handleReview(status: 'KEEP' | 'REJECT'): void {
    if (!shown) return
    patchShown({ status }) // 乐观即时反馈
    enqueueMutation(shown.id, { status }) // 串行落地，连点最终=最后意图
  }

  const lightboxIndex = shown ? Math.max(0, images.findIndex((i) => i.id === shown.id)) : 0

  // 键盘 ←/→ 在 Canvas 内切换当前图片（输入框聚焦时不拦截；Lightbox 打开时由 Lightbox 自己处理）。
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (lightboxOpen) return
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
      const target = event.target as HTMLElement | null
      if (target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) return
      if (images.length < 2) return
      event.preventDefault()
      const currentIndex = shown ? images.findIndex((image) => image.id === shown.id) : -1
      const delta = event.key === 'ArrowLeft' ? -1 : 1
      const nextIndex = currentIndex < 0 ? 0 : (currentIndex + delta + images.length) % images.length
      setSelectedId(images[nextIndex]!.id)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [images, shown, lightboxOpen])

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

        {isQueued && job && (
          <div className="wb4-stage__queued-banner" role="status">
            <span className="muted">已加入队列 · 前方 {queueAhead} 个任务 · 等待开始</span>
            {currentRunningId && currentRunningId !== job.id && (
              <button type="button" className="ds-link" onClick={() => trackJob(currentRunningId)}>
                查看当前运行任务
              </button>
            )}
          </div>
        )}

        {!job && (
          <EmptyState title="暂无生成结果" description="填写 Prompt 并点击“生成”，结果会实时显示在这里。" />
        )}

        {job && shown && (
          <CanvasViewport
            imageUrl={imagePreviewUrl(shown.id)}
            contentUrl={imageContentUrl(shown.id)}
            imageWidth={shown.width}
            imageHeight={shown.height}
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
            ) : isQueued ? (
              <>
                <p className="muted">已加入队列，前方 {queueAhead} 个任务，等待开始…</p>
                <p className="muted">排队期间不显示采样进度，任务开始后这里会实时显示 Step / Stage。</p>
              </>
            ) : (
              <p className="muted">本任务暂无图片</p>
            )}
          </div>
        )}
      </div>

      {error && <p className="ds-notice ds-notice--error">{error}</p>}
      {notice && (
        <p className="ds-notice ds-notice--error" role="alert">
          {notice}
          <button type="button" className="ds-notice__close" onClick={() => setNotice(null)}>知道了</button>
        </p>
      )}

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
                disabled={actionPendingId === shown.id}
                onClick={handleToggleFavorite}
              />
              <IconButton
                icon={<IconKeep size={16} />}
                label="保留"
                disabled={actionPendingId === shown.id}
                onClick={() => handleReview('KEEP')}
              />
              <IconButton
                icon={<IconReject size={16} />}
                label="淘汰"
                disabled={actionPendingId === shown.id}
                onClick={() => handleReview('REJECT')}
              />
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
