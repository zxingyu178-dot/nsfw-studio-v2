import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ApiRequestError, assetApi, imageApi, jobApi, promptApi } from '../../api/client'
import { formatDateTime } from '../../utils/format'
import { emptyWorkbenchSnapshot, snapshotFromState } from '../../stores/workbenchStore'
import {
  Badge,
  Button,
  Drawer,
  Field,
  Input,
  Modal,
  Select,
  StatusBadge,
  Tabs,
} from '../../components/ui'
import {
  ASSET_TYPES,
  IMAGE_KIND_LABEL,
  IMAGE_SOURCE_LABEL,
  IMAGE_STATUS_LABEL,
  MODULE_LABEL,
  imageContentUrl,
  imageThumbUrl,
  normalizeImageStatus,
  shortJobId,
  type AssetType,
  type CleanupRejectedResult,
  type ImageDTO,
  type ImageProvenanceDTO,
  type ImageReviewStatus,
  type ImageSort,
  type ImageVersionsDTO,
  type JobDTO,
  type PromptDTO,
  type ReviewStatus,
  type WorkbenchSnapshot,
} from '../../types/workbench'
import { ImageLightbox } from '../../components/ImageLightbox'
import { ReviewMode } from './ReviewMode'
import './gallery.css'

/**
 * 图库（§四十五-§四十九；Phase 0.11：分页 + 缩略图懒加载 + 审核体系 + Review Mode + 废片清理）。
 * 顶部筛选（全部 / 待审核 / 收藏 / 归档）+ 排序 + 图片 Grid（无限滚动）+ 右侧 Detail Drawer。
 * Review Mode：A 保留 / D 淘汰 / F 收藏 / Space 放大 / ←→ 切换。
 */

const PAGE_SIZE = 40

type TabKey = 'ALL' | 'NEW' | 'FAVORITE' | 'ARCHIVED'
type ViewMode = 'flat' | 'group'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'ALL', label: '全部' },
  { key: 'NEW', label: '待审核' },
  { key: 'FAVORITE', label: '收藏' },
  { key: 'ARCHIVED', label: '归档' },
]

const SORT_OPTIONS: { value: ImageSort; label: string }[] = [
  { value: 'created_desc', label: '最新优先' },
  { value: 'created_asc', label: '最早优先' },
  { value: 'favorite', label: '收藏优先' },
  { value: 'size', label: '尺寸优先' },
]

/** 细分子筛选：在主 Tab 之上叠加 KEEP / REJECT 过滤 */
const SUB_STATUS_OPTIONS: { value: '' | ImageReviewStatus; label: string }[] = [
  { value: '', label: '状态：全部' },
  { value: 'KEEP', label: '保留' },
  { value: 'REJECT', label: '淘汰' },
]

interface UndoEntry {
  imageId: string
  review?: ReviewStatus
  favorite?: boolean
  label: string
}

interface JobSummary {
  job_id: string
  total: number
  unreviewed: number
  kept: number
  rejected: number
  favorites: number
}

export default function GalleryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const jobFilter = searchParams.get('job')

  const [tab, setTab] = useState<TabKey>('ALL')
  const [subStatus, setSubStatus] = useState<'' | ImageReviewStatus>('')
  const [sort, setSort] = useState<ImageSort>('created_desc')
  const [view, setView] = useState<ViewMode>('flat')

  // —— 分页状态 ——
  const [items, setItems] = useState<ImageDTO[]>([])
  const [total, setTotal] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [detail, setDetail] = useState<ImageDTO | null>(null)
  const [groups, setGroups] = useState<{ job: JobDTO; summary: JobSummary }[]>([])
  const [groupsLoading, setGroupsLoading] = useState(false)
  const [selectMode, setSelectMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [upscaling, setUpscaling] = useState(false)
  const [importProgress, setImportProgress] = useState<{ done: number; total: number } | null>(null)
  const importInputRef = useRef<HTMLInputElement | null>(null)
  const [notice, setNotice] = useState<{ text: string; undoable?: boolean } | null>(null)
  const [canUndo, setCanUndo] = useState(false)
  const undoStack = useRef<UndoEntry[]>([])
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const detailTimer = useRef<number | null>(null)

  // Phase 0.11：Review Mode / 清理废片
  const [reviewImages, setReviewImages] = useState<ImageDTO[] | null>(null)
  const [cleanupPreview, setCleanupPreview] = useState<CleanupRejectedResult | null>(null)
  const [cleanupBusy, setCleanupBusy] = useState(false)

  // 分页请求序号（避免快速切换时旧响应覆盖新列表）
  const requestSeq = useRef(0)
  const sentinelRef = useRef<HTMLDivElement | null>(null)

  function statusParam(): ImageReviewStatus | null {
    if (subStatus) return subStatus
    if (tab === 'NEW') return 'NEW'
    if (tab === 'FAVORITE') return 'FAVORITE'
    if (tab === 'ARCHIVED') return 'ARCHIVED'
    return null
  }

  // 第一页 / 切筛选或排序 → 重置列表
  const loadFirst = useCallback(() => {
    const seq = ++requestSeq.current
    setLoading(true)
    setError(null)
    imageApi
      .list({ job_id: jobFilter, status: statusParam(), sort, page: 1, page_size: PAGE_SIZE })
      .then((page) => {
        if (seq !== requestSeq.current) return
        setItems(page.items)
        setTotal(page.total)
        setHasNext(page.has_next)
      })
      .catch((err: unknown) => setError(err instanceof ApiRequestError ? err.message : '加载失败'))
      .finally(() => {
        if (seq === requestSeq.current) setLoading(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, subStatus, sort, jobFilter])

  useEffect(() => {
    loadFirst()
  }, [loadFirst])

  // 追加下一页（无限滚动）
  const loadNext = useCallback(() => {
    if (loadingMore || loading || !hasNext) return
    setLoadingMore(true)
    imageApi
      .list({
        job_id: jobFilter,
        status: statusParam(),
        sort,
        page: Math.floor(items.length / PAGE_SIZE) + 1,
        page_size: PAGE_SIZE,
      })
      .then((page) => {
        setItems((prev) => [...prev, ...page.items])
        setHasNext(page.has_next)
      })
      .catch((err: unknown) => setError(err instanceof ApiRequestError ? err.message : '加载更多失败'))
      .finally(() => setLoadingMore(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadingMore, loading, hasNext, items.length, tab, subStatus, sort, jobFilter])

  // 哨兵进入视口 → 加载下一页
  useEffect(() => {
    const el = sentinelRef.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) void loadNext()
      },
      { rootMargin: '600px' },
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [loadNext])

  useEffect(() => {
    if (view !== 'group' || jobFilter) return
    let cancelled = false
    setGroupsLoading(true)
    jobApi
      .list({ limit: 50 })
      .then(async (page) => {
        const candidates = page.items.filter((job) => job.completed_count > 0).slice(0, 20)
        const summaries = await Promise.all(
          candidates.map((job) => imageApi.jobSummary(job.id).catch(() => null)),
        )
        if (cancelled) return
        setGroups(
          candidates.flatMap((job, index) => {
            const summary = summaries[index]
            return summary ? [{ job, summary }] : []
          }),
        )
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : '无法加载任务分组')
      })
      .finally(() => {
        if (!cancelled) setGroupsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [view, jobFilter])

  function applyJobFilter(jobId: string | null): void {
    const next = new URLSearchParams(searchParams)
    if (jobId) next.set('job', jobId)
    else next.delete('job')
    setSearchParams(next)
  }

  function handleUpdated(updated: ImageDTO): void {
    setItems((previous) => previous.map((item) => (item.id === updated.id ? updated : item)))
    setDetail((current) => (current && current.id === updated.id ? updated : current))
    setReviewImages((prev) => (prev ? prev.map((img) => (img.id === updated.id ? updated : img)) : prev))
  }

  function toggleSelect(imageId: string): void {
    setSelectedIds((previous) =>
      previous.includes(imageId) ? previous.filter((id) => imageId !== id) : [...previous, imageId],
    )
  }

  useEffect(() => {
    return () => {
      if (detailTimer.current !== null) window.clearTimeout(detailTimer.current)
    }
  }, [])

  function handleCardClick(image: ImageDTO): void {
    if (selectMode) {
      toggleSelect(image.id)
      return
    }
    if (detailTimer.current !== null) window.clearTimeout(detailTimer.current)
    detailTimer.current = window.setTimeout(() => {
      detailTimer.current = null
      setDetail(image)
    }, 220)
  }

  function handleCardDoubleClick(image: ImageDTO): void {
    if (detailTimer.current !== null) {
      window.clearTimeout(detailTimer.current)
      detailTimer.current = null
    }
    if (selectMode) return
    const index = items.findIndex((item) => item.id === image.id)
    if (index >= 0) setLightboxIndex(index)
  }

  function openLightboxAt(image: ImageDTO): void {
    const index = items.findIndex((item) => item.id === image.id)
    if (index >= 0) setLightboxIndex(index)
  }

  async function submitUpscale(imageIds: string[]): Promise<JobDTO | null> {
    if (imageIds.length === 0) return null
    setUpscaling(true)
    setNotice(null)
    try {
      const job = await imageApi.upscale(imageIds)
      setNotice({ text: `已创建高清任务 ${shortJobId(job.id)}（${imageIds.length} 张），完成后可在图库查看高清版本` })
      setSelectedIds([])
      setSelectMode(false)
      return job
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '创建高清任务失败')
      return null
    } finally {
      setUpscaling(false)
    }
  }

  async function handleImport(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    if (files.length === 0 || importProgress) return
    setError(null)
    setNotice(null)
    setImportProgress({ done: 0, total: files.length })
    let imported = 0
    let duplicates = 0
    let failed = 0
    const failureMessages: string[] = []
    for (let index = 0; index < files.length; index += 1) {
      try {
        const result = await imageApi.importFiles([files[index]])
        imported += result.imported_count
        duplicates += result.duplicate_count
        failed += result.failed_count
        if (result.failed.length > 0) {
          failureMessages.push(`${result.failed[0].filename}：${result.failed[0].message}`)
        }
      } catch (err) {
        failed += 1
        failureMessages.push(`${files[index].name}：${err instanceof ApiRequestError ? err.message : '导入失败'}`)
      }
      setImportProgress({ done: index + 1, total: files.length })
    }
    setImportProgress(null)
    setNotice({
      text: `导入完成：成功 ${imported} · 已存在 ${duplicates} · 失败 ${failed}${
        failureMessages.length > 0 ? `（${failureMessages.slice(0, 3).join('；')}）` : ''
      }`,
    })
    loadFirst()
  }

  function recordUndo(entry: UndoEntry): void {
    undoStack.current.push(entry)
    if (undoStack.current.length > 20) undoStack.current.shift()
    setCanUndo(true)
  }

  async function undoLast(): Promise<void> {
    const entry = undoStack.current.pop()
    setCanUndo(undoStack.current.length > 0)
    if (!entry) return
    try {
      if (entry.review !== undefined) {
        setDetail((current) =>
          current && current.id === entry.imageId
            ? { ...current, review_status: entry.review as ReviewStatus }
            : current,
        )
        handleUpdated(await imageApi.review(entry.imageId, entry.review))
      }
      if (entry.favorite !== undefined) {
        handleUpdated(await imageApi.favorite(entry.imageId, entry.favorite))
      }
      setNotice({ text: `已撤销${entry.label}` })
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '撤销失败')
    }
  }

  async function quickReview(status: 'KEPT' | 'REJECTED'): Promise<void> {
    if (!detail) return
    recordUndo({ imageId: detail.id, review: detail.review_status, label: status === 'KEPT' ? '保留' : '淘汰' })
    try {
      handleUpdated(await imageApi.review(detail.id, status))
      setNotice({ text: `已${status === 'KEPT' ? '保留' : '淘汰'}`, undoable: true })
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '操作失败')
    }
  }

  async function quickFavorite(): Promise<void> {
    if (!detail) return
    const next = !detail.favorite
    recordUndo({ imageId: detail.id, favorite: detail.favorite, label: next ? '收藏' : '取消收藏' })
    try {
      handleUpdated(await imageApi.favorite(detail.id, next))
      setNotice({ text: next ? '已收藏' : '已取消收藏', undoable: true })
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '操作失败')
    }
  }

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent): void {
      const target = event.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
        return
      }
      if (lightboxIndex !== null || reviewImages !== null) return
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
        event.preventDefault()
        void undoLast()
        return
      }
      if (!detail) return
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        const index = items.findIndex((item) => item.id === detail.id)
        if (index < 0) return
        const next = event.key === 'ArrowLeft' ? index - 1 : index + 1
        if (next >= 0 && next < items.length) setDetail(items[next])
        return
      }
      if (event.key === 'k' || event.key === 'K') void quickReview('KEPT')
      if (event.key === 'r' || event.key === 'R') void quickReview('REJECTED')
      if (event.key === 'f' || event.key === 'F') void quickFavorite()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  })

  function useAsInput(image: ImageDTO): void {
    const snapshot = snapshotFromState()
    snapshot.input_images = [{ role: 'source', image_id: image.id }]
    snapshot.generation_mode = 'image'
    setDetail(null)
    navigate('/generate', { state: { workbench: snapshot, replace: false } })
  }

  /** Phase 0.11：打开当前筛选集合的 Review Mode */
  function startReview(): void {
    if (items.length === 0) return
    setReviewImages(items)
  }

  /** Phase 0.11：按任务打开 Review Mode（仅该 Job 的图） */
  function startReviewJob(jobId: string): void {
    imageApi
      .list({ job_id: jobId, page_size: 200, sort: 'created_asc' })
      .then((page) => {
        if (page.items.length > 0) setReviewImages(page.items)
      })
      .catch((err: unknown) => setError(err instanceof ApiRequestError ? err.message : '无法加载该任务图片'))
  }

  /** Phase 0.11：废片清理——先预览（confirm=false） */
  async function openCleanup(): Promise<void> {
    setCleanupBusy(true)
    setError(null)
    try {
      const result = await imageApi.cleanupRejected({ confirm: false })
      setCleanupPreview(result)
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '无法预览废片清理')
    } finally {
      setCleanupBusy(false)
    }
  }

  async function confirmCleanup(): Promise<void> {
    setCleanupBusy(true)
    try {
      const result = await imageApi.cleanupRejected({ confirm: true })
      setNotice({
        text: `清理完成：已删除 ${result.deleted_count ?? 0} 张，释放 ${formatBytes(result.deleted_bytes ?? 0)}；受保护未删 ${result.protected_count ?? 0} 张`,
      })
      setCleanupPreview(null)
      loadFirst()
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '清理失败')
    } finally {
      setCleanupBusy(false)
    }
  }

  return (
    <>
      <div className="gal-toolbar">
        <Tabs
          ariaLabel="图库筛选"
          active={tab}
          onChange={(key) => setTab(key as TabKey)}
          items={TABS.map(({ key, label }) => ({ key, label }))}
        />
        <Select
          aria-label="审核状态细分"
          value={subStatus}
          onChange={(event) => setSubStatus(event.target.value as '' | ImageReviewStatus)}
          options={SUB_STATUS_OPTIONS.map(({ value, label }) => ({ value, label }))}
        />
        <Select
          aria-label="排序"
          value={sort}
          onChange={(event) => setSort(event.target.value as ImageSort)}
          options={SORT_OPTIONS.map(({ value, label }) => ({ value, label }))}
        />
        <span className="gal-toolbar__spacer" />
        <Button size="sm" variant="primary" onClick={startReview}>
          开始审核
        </Button>
        <Button size="sm" variant="danger" disabled={cleanupBusy} onClick={() => void openCleanup()}>
          {cleanupBusy ? '准备中…' : '清理废片'}
        </Button>
        <Button
          size="sm" variant={selectMode ? 'primary' : 'secondary'}
          onClick={() => { setSelectMode(!selectMode); setSelectedIds([]) }}
        >
          {selectMode ? '退出选择' : '选择'}
        </Button>
        <Button
          size="sm" variant={view === 'group' ? 'primary' : 'secondary'}
          onClick={() => setView(view === 'group' ? 'flat' : 'group')}
        >
          按任务查看
        </Button>
        <Button
          size="sm" variant="secondary"
          disabled={importProgress !== null}
          onClick={() => importInputRef.current?.click()}
        >
          {importProgress ? `导入中 ${importProgress.done} / ${importProgress.total}` : '导入'}
        </Button>
        <input
          ref={importInputRef}
          type="file"
          accept=".jpg,.jpeg,.png,.webp"
          multiple
          hidden
          onChange={(event) => void handleImport(event)}
        />
      </div>

      {selectMode && (
        <div className="gal-toolbar">
          <Badge tone="accent">已选 {selectedIds.length} 张</Badge>
          <Button
            size="sm" variant="primary"
            disabled={upscaling || selectedIds.length === 0}
            onClick={() => void submitUpscale(selectedIds)}
          >
            {upscaling ? '提交中…' : '高清放大'}
          </Button>
          <span className="muted">选择图库已有图片（可多张）→ 创建高清任务，不重复生成原图。</span>
        </div>
      )}

      {notice && (
        <p className="ds-notice ds-notice--success" role="status">
          {notice.text}
          {notice.undoable && canUndo && (
            <Button size="xs" variant="ghost" className="gal-undo-btn" onClick={() => void undoLast()}>
              撤销 (Ctrl+Z)
            </Button>
          )}
        </p>
      )}

      {jobFilter && (
        <div className="gal-toolbar">
          <Badge>任务筛选：{shortJobId(jobFilter)}</Badge>
          <Button size="sm" variant="ghost" onClick={() => applyJobFilter(null)}>
            清除筛选
          </Button>
        </div>
      )}

      {error && <p className="ds-notice ds-notice--error">{error}</p>}

      {/* ===== 按任务分组 ===== */}
      {view === 'group' && !jobFilter && (
        <div className="gal-group-list">
          {groupsLoading && <p className="muted">加载中…</p>}
          {!groupsLoading && groups.length === 0 && (
            <p className="muted">还没有完成过的生成任务。</p>
          )}
          {groups.map(({ job, summary }) => (
            <div key={job.id} className="gal-group">
              <button type="button" className="gal-group__main" onClick={() => applyJobFilter(job.id)}>
                <div className="gal-group__head">
                  <span className="gal-group__id">{shortJobId(job.id)}</span>
                  <span className="muted">{summary.total} 张 · {formatDateTime(job.created_at)}</span>
                </div>
                <p className="gal-group__title">
                  {job.positive_prompt_snapshot.trim().slice(0, 42) || '（无 Prompt）'}
                </p>
                <p className="gal-group__counts muted">
                  未审核 {summary.unreviewed} · 保留 {summary.kept} · 收藏 {summary.favorites} · 淘汰 {summary.rejected}
                </p>
              </button>
              <Button size="sm" variant="primary" onClick={() => startReviewJob(job.id)}>
                开始审核
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* ===== 图片 Grid ===== */}
      {(view === 'flat' || jobFilter) && (
        <>
          {loading && <p className="muted">加载中…</p>}
          {!loading && items.length === 0 && (
            <div className="gal-empty">
              <h2 className="gal-empty__title">还没有图片</h2>
              <p className="muted">在生成工作台创建任务后，生成的图片会逐张进入这里。</p>
            </div>
          )}
          <p className="gal-count">共 {total} 张</p>
          <div className="gal-grid">
            {items.map((image) => {
              const status = normalizeImageStatus(image)
              return (
                <button
                  key={image.id}
                  type="button"
                  className={`gal-card${selectedIds.includes(image.id) ? ' gal-card--selected' : ''}`}
                  onClick={() => handleCardClick(image)}
                  onDoubleClick={() => handleCardDoubleClick(image)}
                  title={`${IMAGE_KIND_LABEL[image.kind] ?? image.kind} · ${shortJobId(image.job_id ?? '')} · ${IMAGE_STATUS_LABEL[status]}`}
                >
                  <GalleryThumb image={image} />
                  <span className="gal-card__badges">
                    {image.kind === 'upscaled' && <span className="gal-card__hd">HD</span>}
                    {selectedIds.includes(image.id) && <Badge tone="accent">✓</Badge>}
                    {status !== 'NEW' && <StatusBadge status={status} />}
                  </span>
                </button>
              )
            })}
          </div>
          {/* 无限滚动哨兵 */}
          {hasNext && <div ref={sentinelRef} className="gal-sentinel" aria-hidden="true" />}
          {loadingMore && <p className="muted">加载更多…</p>}
        </>
      )}

      {detail && (
        <GalleryDetailDrawer
          image={detail}
          onClose={() => setDetail(null)}
          onUpdated={handleUpdated}
          onSelectImage={(image) => {
            setDetail(image)
            setItems((previous) => previous.map((item) => (item.id === image.id ? image : item)))
          }}
          onUpscale={(imageId) => void submitUpscale([imageId])}
          upscaling={upscaling}
          onUseAsInput={useAsInput}
          onReviewStart={(prev) => recordUndo({ imageId: detail.id, review: prev, label: '审核修改' })}
          onFavoriteStart={(prev) => recordUndo({ imageId: detail.id, favorite: prev, label: '收藏修改' })}
          onPreviewLightbox={() => openLightboxAt(detail)}
          onDeleted={() => { setDetail(null); loadFirst() }}
        />
      )}

      {lightboxIndex !== null && (
        <ImageLightbox
          images={items}
          index={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onNavigate={(next) => setLightboxIndex(next)}
        />
      )}

      {reviewImages !== null && (
        <ReviewMode
          images={reviewImages}
          onClose={() => setReviewImages(null)}
          onChanged={handleUpdated}
        />
      )}

      {/* 废片清理两阶段确认 */}
      <Modal
        open={cleanupPreview !== null}
        onClose={() => setCleanupPreview(null)}
        title="清理废片（REJECT）"
        footer={
          <>
            <Button size="sm" variant="secondary" onClick={() => setCleanupPreview(null)}>
              取消
            </Button>
            <Button size="sm" variant="danger" disabled={cleanupBusy} onClick={() => void confirmCleanup()}>
              {cleanupBusy ? '删除中…' : `确认删除 ${cleanupPreview?.candidate_count ?? 0} 张`}
            </Button>
          </>
        }
      >
        <p className="muted">将永久删除以下 REJECT 图片的 original + thumbnail 及数据库记录（不可恢复）。</p>
        <dl className="gal-fields">
          <dt>候选数量</dt>
          <dd>{cleanupPreview?.candidate_count ?? 0} 张</dd>
          <dt>占用空间</dt>
          <dd>{formatBytes(cleanupPreview?.total_bytes ?? 0)}</dd>
          <dt>被引用保护</dt>
          <dd>{cleanupPreview?.protected_count ?? 0} 张（被 Prompt / 素材 / 配方引用，不会删除）</dd>
        </dl>
      </Modal>
    </>
  )
}

/** 人读字节数 */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

/** 卡片缩略图：进入 viewport+300px 才加载，带占位 / 错误重试 */
function GalleryThumb({ image }: { image: ImageDTO }) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [inView, setInView] = useState(false)
  const [error, setError] = useState(false)
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true)
      return
    }
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setInView(true)
          obs.disconnect()
        }
      },
      { rootMargin: '300px' },
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  return (
    <div className="gal-card__media" ref={ref}>
      {!inView ? (
        <div className="gal-card__ph" aria-hidden="true" />
      ) : error ? (
        <div className="gal-card__err" onClick={() => { setError(false); setRetryKey((k) => k + 1) }} role="button" tabIndex={0}>
          加载失败 · 重试
        </div>
      ) : (
        <img
          key={retryKey}
          className="gal-card__img"
          src={imageThumbUrl(image.id)}
          alt=""
          onError={() => setError(true)}
        />
      )}
    </div>
  )
}

// ===== 详情抽屉（§四十六-§四十八；Phase 0.11 信息栏 + 设封面 + 删除） =====

interface DetailDrawerProps {
  image: ImageDTO
  onClose: () => void
  onUpdated: (image: ImageDTO) => void
  onSelectImage: (image: ImageDTO) => void
  onUpscale: (imageId: string) => void
  upscaling: boolean
  onUseAsInput: (image: ImageDTO) => void
  onReviewStart: (previous: ReviewStatus) => void
  onFavoriteStart: (previous: boolean) => void
  onPreviewLightbox: () => void
  onDeleted: () => void
}

function GalleryDetailDrawer({
  image, onClose, onUpdated, onSelectImage, onUpscale, upscaling,
  onUseAsInput, onReviewStart, onFavoriteStart, onPreviewLightbox, onDeleted,
}: DetailDrawerProps) {
  const navigate = useNavigate()
  const [job, setJob] = useState<JobDTO | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [versions, setVersions] = useState<ImageVersionsDTO | null>(null)
  const [provenance, setProvenance] = useState<ImageProvenanceDTO | null>(null)
  const [assetType, setAssetType] = useState<AssetType>('face')
  const [assetName, setAssetName] = useState(`图库-${image.id.replace(/^img_/, '').slice(0, 8)}`)
  // Phase 0.11：设为 Prompt 封面
  const [promptChoices, setPromptChoices] = useState<PromptDTO[]>([])
  const [coverPromptId, setCoverPromptId] = useState('')
  // Phase 0.11：删除确认
  const [deleteArm, setDeleteArm] = useState(false)

  useEffect(() => {
    if (!image.job_id) return
    let cancelled = false
    jobApi
      .get(image.job_id)
      .then((detail) => { if (!cancelled) setJob(detail) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [image.job_id])

  useEffect(() => {
    let cancelled = false
    setVersions(null)
    imageApi
      .versions(image.id)
      .then((result) => { if (!cancelled) setVersions(result) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [image.id])

  useEffect(() => {
    let cancelled = false
    setProvenance(null)
    imageApi
      .provenance(image.id)
      .then((result) => { if (!cancelled) setProvenance(result) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [image.id])

  function run(action: () => Promise<ImageDTO>, okText: string): Promise<void> {
    setBusy(true)
    setError(null)
    setMessage(null)
    return action()
      .then((updated) => {
        onUpdated(updated)
        setMessage(okText)
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : '操作失败')
      })
      .finally(() => setBusy(false))
  }

  function openInWorkbench(useSeed: boolean): void {
    setError(null)
    imageApi
      .workbench(image.id)
      .then((result) => {
        const snapshot = { ...result.snapshot }
        if (useSeed && result.seed !== null) {
          snapshot.seed = result.seed
          snapshot.seed_mode = 'fixed'
          snapshot.count = 1
        }
        onClose()
        navigate('/generate', { state: { workbench: snapshot } })
      })
      .catch((err: unknown) =>
        setError(err instanceof ApiRequestError ? err.message : '无法恢复到工作台'),
      )
  }

  function startImg2Img(): void {
    setError(null)
    const go = (base: WorkbenchSnapshot): void => {
      const snapshot: WorkbenchSnapshot = {
        ...base,
        generation_mode: 'image',
        input_images: [{ role: 'source', image_id: image.id }],
      }
      onClose()
      navigate('/generate', { state: { workbench: snapshot } })
    }
    if (!image.job_id) {
      go(emptyWorkbenchSnapshot())
      return
    }
    imageApi
      .workbench(image.id)
      .then((result) => go(result.snapshot))
      .catch((err: unknown) =>
        setError(err instanceof ApiRequestError ? err.message : '无法恢复原图生成配置'),
      )
  }

  async function createAsset(): Promise<void> {
    if (busy || !assetName.trim()) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const response = await fetch(imageContentUrl(image.id))
      if (!response.ok) throw new Error('图片内容读取失败')
      const blob = await response.blob()
      const suffix = blob.type.includes('jpeg') ? '.jpg' : blob.type.includes('webp') ? '.webp' : '.png'
      const formData = new FormData()
      formData.set('name', assetName.trim())
      formData.set('type', assetType)
      formData.set('prompt_text', job?.positive_prompt_snapshot ?? '')
      formData.set('source_image_id', image.id)
      formData.set(
        'preview',
        new File([blob], `image_${image.id}${suffix}`, { type: blob.type || 'image/png' }),
      )
      await assetApi.create(formData)
      setMessage('素材已创建（独立资产文件，已记录 source_image_id）')
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '创建素材失败')
    } finally {
      setBusy(false)
    }
  }

  function openPromptChooser(): void {
    setError(null)
    setMessage(null)
    promptApi
      .list({ limit: 200 })
      .then((page) => setPromptChoices(page.items))
      .catch((err: unknown) => setError(err instanceof ApiRequestError ? err.message : '无法加载 Prompt 列表'))
  }

  async function applyPromptCover(): Promise<void> {
    if (!coverPromptId) {
      setError('请先选择一个 Prompt')
      return
    }
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await promptApi.setPreviewImage(coverPromptId, image.id)
      setMessage('已设为该 Prompt 封面')
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '设置封面失败')
    } finally {
      setBusy(false)
    }
  }

  async function copyPrompt(): Promise<void> {
    const text = job?.positive_prompt_snapshot ?? ''
    try {
      await navigator.clipboard.writeText(text)
      setMessage('Prompt 已复制')
    } catch {
      setError('复制失败')
    }
  }

  /** 单图删除：复用 cleanup-rejected + 引用保护（confirm=false 预览 → 真删）。 */
  async function deleteImage(): Promise<void> {
    if (!deleteArm) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const preview = await imageApi.cleanupRejected({ image_ids: [image.id], confirm: false })
      if ((preview.protected_count ?? 0) > 0) {
        setError('该图片被 Prompt / 素材 / 配方引用，禁止删除（已保护）。')
        setDeleteArm(false)
        return
      }
      await imageApi.cleanupRejected({ image_ids: [image.id], confirm: true })
      onDeleted()
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '删除失败')
    } finally {
      setBusy(false)
    }
  }

  const displayStatus = normalizeImageStatus(image)

  return (
    <Drawer
      open
      onClose={onClose}
      width="wide"
      title={
        <>
          图片详情
          {displayStatus === 'FAVORITE' && <span title="收藏"> ★</span>}
        </>
      }
    >
      <div className="gal-detail__preview" onDoubleClick={onPreviewLightbox} title="双击放大查看">
        <img src={imageContentUrl(image.id)} alt="" />
        {image.kind === 'upscaled' && <span className="gal-detail__hd">HD</span>}
      </div>

      {(versions?.parent || (versions?.children.length ?? 0) > 0) && (
        <div className="gal-version-links">
          {versions?.parent && (
            <Button size="sm" variant="ghost" onClick={() => onSelectImage(versions.parent as ImageDTO)}>
              来源原图：{IMAGE_KIND_LABEL[versions.parent.kind] ?? versions.parent.kind} · 查看
            </Button>
          )}
          {(versions?.children.length ?? 0) > 0 && (
            <div className="gal-version-children">
              <span className="muted">派生版本：</span>
              {versions!.children.map((child) => {
                const scale = image.width > 0 ? Math.round(child.width / image.width) : 0
                return (
                  <Button
                    key={child.id}
                    size="sm" variant="ghost"
                    onClick={() => onSelectImage(child)}
                  >
                    {IMAGE_KIND_LABEL[child.kind] ?? child.kind}
                    {scale > 1 ? ` ×${scale}` : ''} · {child.width}×{child.height}
                  </Button>
                )
              })}
            </div>
          )}
        </div>
      )}

      <div className="gal-actions">
        <Button
          size="sm" variant={image.review_status === 'KEPT' ? 'primary' : 'secondary'}
          disabled={busy}
          onClick={() => { onReviewStart(image.review_status); void run(() => imageApi.review(image.id, 'KEPT'), '已保留') }}
        >
          保留 (K)
        </Button>
        <Button
          size="sm" variant={image.review_status === 'REJECTED' ? 'primary' : 'secondary'}
          disabled={busy}
          onClick={() => { onReviewStart(image.review_status); void run(() => imageApi.review(image.id, 'REJECTED'), '已淘汰') }}
        >
          淘汰 (R)
        </Button>
        {image.review_status !== 'UNREVIEWED' && (
          <Button
            size="sm" variant="ghost" disabled={busy}
            onClick={() => { onReviewStart(image.review_status); void run(() => imageApi.review(image.id, 'UNREVIEWED'), '已恢复为未审核') }}
          >
            取消审核
          </Button>
        )}
        <Button
          size="sm" variant="ghost" disabled={busy}
          onClick={() => { onFavoriteStart(image.favorite); void run(() => imageApi.favorite(image.id, !image.favorite), image.favorite ? '已取消收藏' : '已收藏') }}
        >
          {image.favorite ? '★ 已收藏' : '☆ 收藏 (F)'}
        </Button>
      </div>

      {provenance && (
        <div>
          <dl className="gal-fields">
            <dt>来源任务</dt>
            <dd>{provenance.job_id ? shortJobId(provenance.job_id) : '外部导入'}</dd>
            <dt>Seed</dt>
            <dd>{provenance.seed ?? '—'}</dd>
            <dt>管线</dt>
            <dd>
              {!provenance.job_id
                ? '外部导入'
                : provenance.kind === 'upscaled'
                  ? `基础生成 → 高清${provenance.scale && provenance.scale > 1 ? ` ×${provenance.scale}` : ''}`
                  : MODULE_LABEL[provenance.module_id ?? ''] ?? provenance.module_id ?? '—'}
            </dd>
          </dl>
          <details>
            <summary className="muted">高级信息（来源原图 / Stage / Workflow 版本）</summary>
            <dl className="gal-fields">
              <dt>来源原图</dt>
              <dd>{provenance.parent_image_id ?? '（本身为原图）'}</dd>
              <dt>Stage</dt>
              <dd>{provenance.stage_index ?? '—'}</dd>
              <dt>模块</dt>
              <dd>{provenance.module_id ?? '—'}{provenance.module_version ? ` ${provenance.module_version}` : ''}</dd>
              <dt>引擎 / Binding</dt>
              <dd>{provenance.provider ?? '—'}{provenance.binding_version ? ` ${provenance.binding_version}` : ''}</dd>
              <dt>workflow_hash</dt>
              <dd>{provenance.workflow_hash ?? '—'}</dd>
              <dt>binding_hash</dt>
              <dd>{provenance.binding_hash ?? '—'}</dd>
            </dl>
          </details>
        </div>
      )}

      <div className="gal-actions">
        <Button size="sm" variant="primary" disabled={!image.job_id} onClick={() => openInWorkbench(false)}>
          在生成工作台中打开
        </Button>
        <Button size="sm" variant="secondary" disabled={!image.job_id} onClick={() => openInWorkbench(true)}>
          使用原图 Seed
        </Button>
        <Button size="sm" variant="secondary" onClick={() => onUseAsInput(image)}>
          用作输入图片
        </Button>
        <Button size="sm" variant="secondary" onClick={startImg2Img}>
          以此图进行图生图
        </Button>
        <Button size="sm" variant="secondary" disabled={upscaling} onClick={() => onUpscale(image.id)}>
          {upscaling ? '提交中…' : '高清放大'}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => void copyPrompt()}>
          复制 Prompt
        </Button>
      </div>

      {message && <p className="ds-notice ds-notice--success" role="status">{message}</p>}
      {error && <p className="ds-notice ds-notice--error">{error}</p>}

      <dl className="gal-fields">
        <dt>Prompt</dt>
        <dd><pre>{job?.positive_prompt_snapshot || '（不可用）'}</pre></dd>
        <dt>Negative</dt>
        <dd><pre>{job?.negative_prompt_snapshot || '（无）'}</pre></dd>
        <dt>Seed</dt>
        <dd>{image.seed ?? '—'}</dd>
        <dt>任务</dt>
        <dd>{image.job_id ? shortJobId(image.job_id) : '—（导入图片）'}</dd>
        <dt>类型</dt>
        <dd>{IMAGE_KIND_LABEL[image.kind] ?? image.kind}</dd>
        <dt>来源</dt>
        <dd>{IMAGE_SOURCE_LABEL[image.source] ?? image.source}</dd>
        <dt>时间</dt>
        <dd>{formatDateTime(image.created_at)}</dd>
        <dt>尺寸</dt>
        <dd>{image.width} × {image.height}</dd>
        <dt>审核</dt>
        <dd>{IMAGE_STATUS_LABEL[displayStatus]}</dd>
      </dl>

      {/* 从图库创建素材（§四十八） */}
      <section className="gal-asset-edit">
        <h4 className="gal-section-title">创建素材（独立资产文件，图片以后被清理不影响素材）</h4>
        <Field label="类型">
          <Select
            value={assetType}
            onChange={(event) => setAssetType(event.target.value as AssetType)}
            options={ASSET_TYPES.map(({ key, label }) => ({ value: key, label }))}
          />
        </Field>
        <Field label="名称">
          <Input value={assetName} onChange={(event) => setAssetName(event.target.value)} />
        </Field>
        <Button
          size="sm" variant="primary"
          disabled={busy || !assetName.trim()}
          onClick={() => void createAsset()}
        >
          创建素材
        </Button>
      </section>

      {/* Phase 0.11：设为 Prompt 封面 */}
      <section className="gal-asset-edit">
        <h4 className="gal-section-title">设为 Prompt 封面</h4>
        {promptChoices.length === 0 ? (
          <Button size="sm" variant="secondary" disabled={busy} onClick={openPromptChooser}>
            选择 Prompt
          </Button>
        ) : (
          <>
            <Field label="Prompt">
              <Select
                value={coverPromptId}
                onChange={(event) => setCoverPromptId(event.target.value)}
                options={[{ value: '', label: '（请选择）' }, ...promptChoices.map((p) => ({ value: p.id, label: p.name }))]}
              />
            </Field>
            <Button size="sm" variant="primary" disabled={busy || !coverPromptId} onClick={() => void applyPromptCover()}>
              设为封面
            </Button>
          </>
        )}
      </section>

      {/* Phase 0.11：删除（引用保护） */}
      <section className="gal-asset-edit">
        <h4 className="gal-section-title">删除图片</h4>
        <p className="muted">删除前会检查引用；被 Prompt / 素材 / 配方引用的图片将被保护，不会删除。</p>
        {!deleteArm ? (
          <Button size="sm" variant="danger" disabled={busy} onClick={() => setDeleteArm(true)}>
            删除此图片
          </Button>
        ) : (
          <div className="gal-actions">
            <Button size="sm" variant="danger" disabled={busy} onClick={() => void deleteImage()}>
              {busy ? '处理中…' : '确认删除（不可恢复）'}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setDeleteArm(false)}>
              取消
            </Button>
          </div>
        )}
      </section>
    </Drawer>
  )
}
