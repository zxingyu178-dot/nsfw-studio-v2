import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ApiRequestError, imageApi, type ImageStatsParams } from '../../api/client'
import { emptyWorkbenchSnapshot } from '../../stores/workbenchStore'
import { Badge, Button, ConfirmModal } from '../../components/ui'
import {
  normalizeImageStatus,
  shortJobId,
  type CleanupRejectedResult,
  type ImageDTO,
  type ImageReviewStatus,
} from '../../types/workbench'
import { ImageLightbox } from '../../components/ImageLightbox'
import { LightboxInfoPanel } from '../../components/LightboxInfoPanel'
import { ReviewMode, type ReviewPageLoader } from './ReviewMode'
import { useGalleryQuery, type GallerySource } from './hooks/useGalleryQuery'
import { useGallerySelection } from './hooks/useGallerySelection'
import { useGalleryPrefs } from './hooks/useGalleryPrefs'
import { createReviewSessionAdapter, type ReviewSessionAdapter } from './hooks/useReviewSession'
import { GalleryToolbar } from './components/GalleryToolbar'
import { GalleryGrid } from './components/GalleryGrid'
import { GallerySelectionBar } from './components/GallerySelectionBar'
import { GalleryGroupView } from './components/GalleryGroupView'
import { GalleryDetailDrawer } from './components/GalleryDetailDrawer'
import { CleanupRejectedDialog } from './components/CleanupRejectedDialog'
import './gallery.css'

/**
 * 图库（§四十五-§四十九；Phase 0.11：分页 + 缩略图懒加载 + 审核体系 + Review Mode + 废片清理）。
 * Phase 0.12 Task9：拆分为 Toolbar / Grid / Card / GroupView / SelectionBar / DetailDrawer /
 * CleanupDialog + useGalleryQuery / useGallerySelection hooks；本文件仅做编排，行为不变。
 */

interface UndoEntry {
  imageId: string
  status?: ImageReviewStatus
  favorite?: boolean
  label: string
}

type BatchReviewStatus = 'KEEP' | 'REJECT' | 'ARCHIVED'

interface PendingBatchReview {
  status: BatchReviewStatus
  ids: string[]
}

const BATCH_STATUS_LIMIT = 500

function batchActionLabel(status: BatchReviewStatus): string {
  if (status === 'KEEP') return '保留'
  if (status === 'REJECT') return '淘汰'
  return '归档'
}

export default function GalleryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const jobFilter = searchParams.get('job')
  const sourceParam = searchParams.get('source')
  const sourceFilter: GallerySource =
    sourceParam === 'comfyui' || sourceParam === 'import' ? sourceParam : ''

  const [view, setView] = useState<'flat' | 'group'>('flat')

  const query = useGalleryQuery(jobFilter, sourceFilter)
  const selection = useGallerySelection()
  const prefs = useGalleryPrefs()

  const [detail, setDetail] = useState<ImageDTO | null>(null)
  const detailTimer = useRef<number | null>(null)

  const [upscaling, setUpscaling] = useState(false)
  const [selectingAll, setSelectingAll] = useState(false)
  const [batchBusy, setBatchBusy] = useState(false)
  const [pendingBatchReview, setPendingBatchReview] = useState<PendingBatchReview | null>(null)
  const [importProgress, setImportProgress] = useState<{ done: number; total: number } | null>(null)
  const importInputRef = useRef<HTMLInputElement | null>(null)
  const [notice, setNotice] = useState<{ text: string; undoable?: boolean } | null>(null)
  const [canUndo, setCanUndo] = useState(false)
  const undoStack = useRef<UndoEntry[]>([])
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)

  // Phase 0.11.1：Review Session（分页 loader，全历史审核）
  const [reviewSession, setReviewSession] = useState<{
    loader: ReviewPageLoader
    adapter?: ReviewSessionAdapter
    title?: string
    total?: number
    statsParams?: ImageStatsParams
  } | null>(null)
  const [cleanupPreview, setCleanupPreview] = useState<CleanupRejectedResult | null>(null)
  const [cleanupImageIds, setCleanupImageIds] = useState<string[] | null>(null)
  const [cleanupBusy, setCleanupBusy] = useState(false)

  useEffect(() => {
    if (sourceParam === null || sourceFilter !== '') return
    const next = new URLSearchParams(searchParams)
    next.delete('source')
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams, sourceFilter, sourceParam])

  // 按任务分组：进入 group 视图且无 jobFilter 时加载第一页
  useEffect(() => {
    if (view !== 'group' || jobFilter) return
    query.resetGroups()
    query.loadGroups(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, jobFilter, query.loadGroups])

  function applyJobFilter(jobId: string | null): void {
    const next = new URLSearchParams(searchParams)
    if (jobId) next.set('job', jobId)
    else next.delete('job')
    setSearchParams(next)
  }

  function applySourceFilter(source: GallerySource): void {
    const next = new URLSearchParams(searchParams)
    if (source) next.set('source', source)
    else next.delete('source')
    setSearchParams(next)
  }

  function handleUpdated(updated: ImageDTO): void {
    query.applyItemUpdated(updated)
    setDetail((current) => (current && current.id === updated.id ? updated : current))
  }

  /** Phase 0.18 C：卡片 hover 操作层的收藏切换（失败回写到页面错误条）。 */
  async function handleToggleFavorite(image: ImageDTO): Promise<void> {
    try {
      handleUpdated(await imageApi.favorite(image.id, !image.favorite))
    } catch (err) {
      query.setError(err instanceof ApiRequestError ? err.message : '收藏操作失败')
    }
  }

  useEffect(() => {
    return () => {
      if (detailTimer.current !== null) window.clearTimeout(detailTimer.current)
    }
  }, [])

  function handleCardClick(image: ImageDTO): void {
    if (selection.selectMode) {
      selection.toggleSelect(image.id)
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
    if (selection.selectMode) return
    const index = query.items.findIndex((item) => item.id === image.id)
    if (index >= 0) setLightboxIndex(index)
  }

  function openLightboxAt(image: ImageDTO): void {
    const index = query.items.findIndex((item) => item.id === image.id)
    if (index >= 0) setLightboxIndex(index)
  }

  async function submitUpscale(imageIds: string[]): Promise<unknown> {
    if (imageIds.length === 0) return null
    setUpscaling(true)
    setNotice(null)
    try {
      const job = await imageApi.upscale(imageIds)
      setNotice({ text: `已创建高清任务 ${shortJobId(job.id)}（${imageIds.length} 张），完成后可在图库查看高清版本` })
      selection.exitSelect()
      return job
    } catch (err) {
      query.setError(err instanceof ApiRequestError ? err.message : '创建高清任务失败')
      return null
    } finally {
      setUpscaling(false)
    }
  }

  async function selectCurrentFilter(): Promise<void> {
    setSelectingAll(true)
    query.setError(null)
    setNotice(null)
    try {
      const { page: _page, page_size: _pageSize, ...filters } = query.listQuery()
      const result = await imageApi.ids(filters)
      selection.setSelectedIds(result.ids)
      if (result.truncated || result.total > result.ids.length) {
        setNotice({ text: `仅选中前 ${result.ids.length} 张（当前筛选共 ${result.total} 张）` })
      }
    } catch (err) {
      query.setError(err instanceof ApiRequestError ? err.message : '全选当前筛选失败')
    } finally {
      setSelectingAll(false)
    }
  }

  /** 批量审核按后端上限顺序分块；失败时保留选择，便于用户判断后续动作。 */
  async function batchReview(status: BatchReviewStatus, ids: string[]): Promise<void> {
    if (ids.length === 0) return
    const action = batchActionLabel(status)
    let processed = 0
    let updated = 0
    setBatchBusy(true)
    query.setError(null)
    setNotice({ text: `${action}中 0/${ids.length}` })
    try {
      for (let start = 0; start < ids.length; start += BATCH_STATUS_LIMIT) {
        const chunk = ids.slice(start, start + BATCH_STATUS_LIMIT)
        // 后端限制每次最多 500 个 ID，必须保持顺序逐块提交。
        // eslint-disable-next-line no-await-in-loop
        const result = await imageApi.batchStatus({ image_ids: chunk, status })
        processed += chunk.length
        updated += result.updated ?? chunk.length
        setNotice({ text: `${action}中 ${processed}/${ids.length}` })
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '批量操作失败'
      query.setError(`${action}失败：已成功 ${updated}/${ids.length} 张；${message}`)
      setNotice(null)
      return
    } finally {
      setBatchBusy(false)
    }
    setNotice({ text: `已${action} ${updated} 张` })
    query.loadFirst()
    selection.exitSelect()
  }

  function requestBatchReview(status: BatchReviewStatus): void {
    const ids = [...selection.selectedIds]
    if (ids.length === 0) return
    if ((status === 'REJECT' || status === 'ARCHIVED') && ids.length > 100) {
      setPendingBatchReview({ status, ids })
      return
    }
    void batchReview(status, ids)
  }

  async function batchFavorite(): Promise<void> {
    const ids = selection.selectedIds
    if (ids.length === 0) return
    setNotice(null)
    try {
      for (const id of ids) {
        // eslint-disable-next-line no-await-in-loop
        handleUpdated(await imageApi.favorite(id, true))
      }
      setNotice({ text: `已收藏 ${ids.length} 张` })
      selection.exitSelect()
    } catch (err) {
      query.setError(err instanceof ApiRequestError ? err.message : '批量收藏失败')
    }
  }

  async function handleImport(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    if (files.length === 0 || importProgress) return
    query.setError(null)
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
    query.loadFirst()
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
      if (entry.status !== undefined) {
        handleUpdated(await imageApi.setStatus(entry.imageId, { status: entry.status }))
      }
      if (entry.favorite !== undefined) {
        handleUpdated(await imageApi.favorite(entry.imageId, entry.favorite))
      }
      setNotice({ text: `已撤销${entry.label}` })
    } catch (err) {
      query.setError(err instanceof ApiRequestError ? err.message : '撤销失败')
    }
  }

  async function quickReview(status: 'KEEP' | 'REJECT'): Promise<void> {
    if (!detail) return
    const prev = normalizeImageStatus(detail)
    recordUndo({ imageId: detail.id, status: prev, label: status === 'KEEP' ? '保留' : '淘汰' })
    try {
      handleUpdated(await imageApi.setStatus(detail.id, { status }))
      setNotice({ text: `已${status === 'KEEP' ? '保留' : '淘汰'}`, undoable: true })
    } catch (err) {
      query.setError(err instanceof ApiRequestError ? err.message : '操作失败')
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
      query.setError(err instanceof ApiRequestError ? err.message : '操作失败')
    }
  }

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent): void {
      const target = event.target as HTMLElement | null
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
        return
      }
      if (lightboxIndex !== null || reviewSession !== null) return
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
        event.preventDefault()
        void undoLast()
        return
      }
      if (!detail) return
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        const index = query.items.findIndex((item) => item.id === detail.id)
        if (index < 0) return
        const next = event.key === 'ArrowLeft' ? index - 1 : index + 1
        if (next >= 0 && next < query.items.length) setDetail(query.items[next])
        return
      }
      if (event.key === 'k' || event.key === 'K') void quickReview('KEEP')
      if (event.key === 'r' || event.key === 'R') void quickReview('REJECT')
      if (event.key === 'f' || event.key === 'F') void quickFavorite()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  })

  function useAsInput(image: ImageDTO): void {
    const snapshot = emptyWorkbenchSnapshot()
    snapshot.input_images = [{ role: 'source', image_id: image.id }]
    snapshot.generation_mode = 'image'
    setDetail(null)
    navigate('/generate', { state: { workbench: snapshot, replace: false } })
  }

  /** Phase 0.13：开始审核 → 冻结式审核会话（/api/v1/review/*，与手机桥共用 ImageReviewSessionService）。
   *  绝对 index 队列替代 status=NEW 动态 offset 翻页；GET sessions/latest 断点续看。 */
  function startReview(): void {
    const adapter = createReviewSessionAdapter({ status: 'NEW', sort: 'created_desc' })
    setReviewSession({
      title: '图库审核',
      statsParams: { status: 'NEW' },
      adapter,
      loader: {
        loadPage: (page) => adapter.loadPage(page),
      },
    })
  }

  /** Phase 0.11.1：按 Job 打开 Review Mode——取消 page_size=100 上限，分页拉全直到 has_next=false */
  function startReviewJob(jobId: string): void {
    setReviewSession({
      title: `任务 ${shortJobId(jobId)}`,
      statsParams: { job_id: jobId },
      loader: {
        loadPage: (page) =>
          imageApi
            .list({ job_id: jobId, sort: 'created_asc', page, page_size: query.listQuery().page_size })
            .then((p) => ({ items: p.items, has_next: p.has_next, total: p.total })),
      },
    })
  }

  /** 废片清理——全局入口不传 image_ids，多选入口冻结当前选择并复用同一确认对话框。 */
  async function openCleanup(imageIds?: string[]): Promise<void> {
    const targetIds = imageIds ? [...imageIds] : null
    setCleanupBusy(true)
    query.setError(null)
    try {
      const result = await imageApi.cleanupRejected({
        ...(targetIds ? { image_ids: targetIds } : {}),
        confirm: false,
      })
      setCleanupImageIds(targetIds)
      setCleanupPreview(result)
    } catch (err) {
      query.setError(err instanceof ApiRequestError ? err.message : '无法预览废片清理')
    } finally {
      setCleanupBusy(false)
    }
  }

  async function confirmCleanup(): Promise<void> {
    setCleanupBusy(true)
    query.setError(null)
    try {
      const result = await imageApi.cleanupRejected({
        ...(cleanupImageIds ? { image_ids: cleanupImageIds } : {}),
        confirm: true,
      })
      // eslint-disable-next-line no-console
      const bytes = result.deleted_bytes ?? 0
      const released = bytes < 1024 ? `${bytes} B`
        : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB`
        : bytes < 1024 * 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
        : `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
      setNotice({
        text: `清理完成：已删除 ${result.deleted_count ?? 0} 张，释放 ${released}；受保护未删 ${result.protected_count ?? 0} 张`,
      })
      setCleanupPreview(null)
      setCleanupImageIds(null)
      query.loadFirst()
      if (cleanupImageIds) selection.exitSelect()
      try {
        await imageApi.stats(query.buildStatsParams())
      } catch (err) {
        query.setError(err instanceof ApiRequestError ? err.message : '统计刷新失败')
      }
    } catch (err) {
      query.setError(err instanceof ApiRequestError ? err.message : '清理失败')
    } finally {
      setCleanupBusy(false)
    }
  }

  return (
    <>
      <GalleryToolbar
        tab={query.tab}
        onTabChange={query.setTab}
        view={view}
        onToggleView={() => setView(view === 'group' ? 'flat' : 'group')}
        subStatus={query.subStatus}
        onSubStatusChange={query.setSubStatus}
        source={sourceFilter}
        onSourceChange={applySourceFilter}
        sort={query.sort}
        onSortChange={query.setSort}
        density={prefs.density}
        onDensityChange={prefs.setDensity}
        selectMode={selection.selectMode}
        onToggleSelect={selection.toggleSelectMode}
        onStartReview={startReview}
        cleanupBusy={cleanupBusy}
        onOpenCleanup={() => void openCleanup()}
        importProgress={importProgress}
        importInputRef={importInputRef}
        onImportChange={(event) => void handleImport(event)}
      />

      {selection.selectMode && (
        <GallerySelectionBar
          count={selection.selectedIds.length}
          upscaling={upscaling}
          selectingAll={selectingAll}
          busy={batchBusy}
          onSelectAll={() => void selectCurrentFilter()}
          onUpscale={() => void submitUpscale(selection.selectedIds)}
          onBatchKeep={() => requestBatchReview('KEEP')}
          onBatchReject={() => requestBatchReview('REJECT')}
          onBatchArchive={() => requestBatchReview('ARCHIVED')}
          onDelete={() => void openCleanup(selection.selectedIds)}
          onBatchFavorite={() => void batchFavorite()}
          onExitSelect={selection.exitSelect}
        />
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

      {query.error && <p className="ds-notice ds-notice--error">{query.error}</p>}

      {/* ===== 按任务分组 ===== */}
      {view === 'group' && !jobFilter && (
        <GalleryGroupView
          groups={query.groups}
          loading={query.groupsLoading}
          hasNext={query.groupsHasNext}
          page={query.groupsPage}
          onApplyJobFilter={applyJobFilter}
          onReviewJob={startReviewJob}
          onLoadMore={query.loadGroups}
        />
      )}

      {/* ===== 图片 Grid ===== */}
      {(view === 'flat' || jobFilter) && (
        <GalleryGrid
          items={query.items}
          total={query.total}
          hasNext={query.hasNext}
          loading={query.loading}
          loadingMore={query.loadingMore}
          selectedIds={selection.selectedIds}
          selectMode={selection.selectMode}
          density={prefs.density}
          fit={prefs.fit}
          onCardClick={handleCardClick}
          onCardDoubleClick={handleCardDoubleClick}
          onToggleFavorite={handleToggleFavorite}
          sentinelRef={query.sentinelRef}
        />
      )}

      {detail && (
        <GalleryDetailDrawer
          image={detail}
          onClose={() => setDetail(null)}
          onUpdated={handleUpdated}
          onSelectImage={(image) => {
            setDetail(image)
            query.applyItemUpdated(image)
          }}
          onUpscale={(imageId) => void submitUpscale([imageId])}
          upscaling={upscaling}
          onUseAsInput={useAsInput}
          onReviewStart={(prev) => recordUndo({ imageId: detail.id, status: prev, label: '审核修改' })}
          onFavoriteStart={(prev) => recordUndo({ imageId: detail.id, favorite: prev, label: '收藏修改' })}
          onPreviewLightbox={() => openLightboxAt(detail)}
          onDeleted={() => { setDetail(null); query.loadFirst() }}
        />
      )}

      {lightboxIndex !== null && (
        <ImageLightbox
          images={query.items}
          index={lightboxIndex}
          hasMore={query.hasNext}
          onLoadMore={() => query.loadNext()}
          loadingMore={query.loadingMore}
          onClose={() => setLightboxIndex(null)}
          onNavigate={(next) => setLightboxIndex(next)}
          renderSidePanel={(img) => (
            <LightboxInfoPanel
              image={img}
              onUpdated={(u) => query.applyItemUpdated(u)}
              onDeleted={(deletedId) => {
                query.removeItem(deletedId)
                setLightboxIndex(null)
              }}
            />
          )}
        />
      )}

      {reviewSession !== null && (
        <ReviewMode
          loader={reviewSession.loader}
          total={reviewSession.total}
          statsParams={reviewSession.statsParams}
          sessionAdapter={reviewSession.adapter}
          title={reviewSession.title}
          onClose={() => setReviewSession(null)}
          onChanged={handleUpdated}
        />
      )}

      <CleanupRejectedDialog
        preview={cleanupPreview}
        busy={cleanupBusy}
        onCancel={() => { setCleanupPreview(null); setCleanupImageIds(null) }}
        onConfirm={() => void confirmCleanup()}
      />

      <ConfirmModal
        open={pendingBatchReview !== null}
        title={pendingBatchReview
          ? `确认${batchActionLabel(pendingBatchReview.status)} ${pendingBatchReview.ids.length} 张图片？`
          : '确认批量操作？'}
        message={pendingBatchReview
          ? `将${batchActionLabel(pendingBatchReview.status)}已选的 ${pendingBatchReview.ids.length} 张图片。此操作将分批执行。`
          : ''}
        confirmText={pendingBatchReview ? `确认${batchActionLabel(pendingBatchReview.status)}` : '确认'}
        cancelText="取消"
        danger={pendingBatchReview?.status === 'REJECT'}
        onCancel={() => setPendingBatchReview(null)}
        onConfirm={() => {
          if (!pendingBatchReview) return
          const pending = pendingBatchReview
          setPendingBatchReview(null)
          void batchReview(pending.status, pending.ids)
        }}
      />
    </>
  )
}
