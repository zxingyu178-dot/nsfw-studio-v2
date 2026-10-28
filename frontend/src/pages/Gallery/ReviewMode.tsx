import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiRequestError,
  imageApi,
  type ImageStatsParams,
  type ReviewQueueImageDTO,
  type ReviewSessionSummaryDTO,
} from '../../api/client'
import {
  imageContentUrl,
  imagePreviewUrl,
  normalizeImageStatus,
  type ImageDTO,
  type ImageReviewStatus,
  type ImageStatsResponse,
} from '../../types/workbench'
import type { ReviewBatchMode, ReviewSessionAdapter, SessionImage } from './hooks/useReviewSession'
import './review-mode.css'

/**
 * Phase 0.11.1 摄影选片式 Review Mode（全屏）。
 *
 * - 居中大图 + ←/→ 切换 + ✅保留 / ⭐收藏 / ❌淘汰；
 * - 快捷键：← 上一张、→ 下一张、A 保留、D 淘汰、F 收藏、Space 放大、Ctrl+Z 撤销上一条、ESC 关闭；
 * - 打标后自动跳到下一张；顶部进度 + 全局统计（imageApi.stats server 端聚合）+ 剩余待审。
 *
 * Phase 0.12：
 * - 统计改用 imageApi.stats（修正"分母 server total、分子本地 list"的假全局）；
 * - ReviewMode 自维护 undo stack，Ctrl+Z 撤销上一条打标/收藏；
 * - 队列耗尽（无下一页且到末尾）显示结束态：本次审核完成 保留X/淘汰X/收藏X + [返回图库][继续审核下一批]；
 * - 跨分页：has_next 预取直到 false。
 *
 * v0.37（P0-A）：
 * - 新图不再被旧冻结会话挡住：头部「检查新图」走真实 DB 计数，可显式换批；
 * - 结束态提供「审新一批（仅新图）」与「审核全部未审核」两种显式入口；
 * - 换批 = 放弃旧 ACTIVE 会话（保留 items）+ 新建冻结队列，索引不重排、队列不压缩。
 */

/** 分页加载器：page 从 1 起。返回本页 items + 是否还有下一页 + 服务端 total。
 *  Phase 0.13：冻结会话首屏可带 startPage / initialIndex（断点续看定位）。 */
export interface ReviewPageLoaderResult {
  items: ImageDTO[]
  has_next: boolean
  total: number
  initialIndex?: number
  startPage?: number
}

export interface ReviewPageLoader {
  loadPage: (page: number) => Promise<ReviewPageLoaderResult>
}

export interface ReviewModeProps {
  /** 静态集合模式（与 loader 二选一；优先） */
  images?: ImageDTO[]
  /** 分页会话模式 */
  loader?: ReviewPageLoader
  /** 服务端 total（用于进度分母；缺省用已加载数量） */
  total?: number
  /** Phase 0.12：全局统计过滤参数（与 list 同口径）；传入后顶部改用 server stats */
  statsParams?: ImageStatsParams
  /** Phase 0.13：冻结审核会话适配器。传入后打标/收藏/撤销/409 冲突同步
   *  全部走 /api/v1/review/*（与手机共用 ImageReviewSessionService）；
   *  缺省回落旧 imageApi.setStatus/favorite（静态集合模式行为不变）。 */
  sessionAdapter?: ReviewSessionAdapter
  initialIndex?: number
  title?: string
  onClose: () => void
  /** 单张打标后同步回 Gallery 列表（保持 Grid 徽标一致） */
  onChanged?: (image: ImageDTO) => void
}

interface UndoEntry {
  image: ImageDTO
  prevStatus: ImageReviewStatus
  prevFavorite: boolean
}

/** 从 409 REVIEW_CONFLICT 错误体里取权威 Image（桌面 8000 当前剥离 details，可能拿不到） */
function conflictAuthoritativeImage(err: unknown): ReviewQueueImageDTO | undefined {
  if (err instanceof ApiRequestError && err.details && typeof err.details === 'object') {
    const image = (err.details as { image?: unknown }).image
    if (image && typeof image === 'object') return image as ReviewQueueImageDTO
  }
  return undefined
}

export function ReviewMode({ images, loader, total, statsParams, sessionAdapter, initialIndex = 0, title, onClose, onChanged }: ReviewModeProps) {
  const [list, setList] = useState<ImageDTO[]>(images ?? [])
  const [index, setIndex] = useState(() =>
    Math.min(Math.max(initialIndex, 0), Math.max((images?.length ?? 1) - 1, 0)),
  )
  const [zoomed, setZoomed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasNext, setHasNext] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [serverTotal, setServerTotal] = useState<number | null>(total ?? null)

  // Phase 0.12：全局统计（server 端聚合）+ 本次会话打标计数 + undo stack
  const [serverStats, setServerStats] = useState<ImageStatsResponse | null>(null)
  const [sessionKept, setSessionKept] = useState(0)
  const [sessionRejected, setSessionRejected] = useState(0)
  const [sessionFavorited, setSessionFavorited] = useState(0)
  // 结束态：仅当用户在队列末尾再按"下一张"（越界前进且无下一页）时进入；
  // 普通浏览 / 放大最后一张不会被结束态覆盖。
  const [finished, setFinished] = useState(false)
  // v0.37：当前批次摘要 + 批次之外的待审图片数量 + 显式换批状态
  const [batchInfo, setBatchInfo] = useState<ReviewSessionSummaryDTO | null>(null)
  const [newCount, setNewCount] = useState<number | null>(null)
  const [switching, setSwitching] = useState(false)
  const batchSeqRef = useRef(0)
  const undoRef = useRef<UndoEntry[]>([])

  const loadedPageRef = useRef(0)
  const prefetchSeqRef = useRef(0)

  const refreshStats = useCallback(() => {
    if (!statsParams || typeof imageApi.stats !== 'function') return
    imageApi
      .stats(statsParams)
      .then((s) => setServerStats(s))
      .catch((err: unknown) => {
        // 统计只影响顶部辅助信息，失败不打断审核，但要留下可诊断记录
        console.warn('[review] 统计刷新失败', err)
      })
  }, [statsParams])

  useEffect(() => {
    refreshStats()
  }, [refreshStats])

  /** 真实 DB 计数：当前批次之外还有多少张待审（含换批后新生成的图）。 */
  const checkNewCount = useCallback(async (): Promise<void> => {
    if (!sessionAdapter) return
    try {
      setNewCount(await sessionAdapter.countOutsideBatch())
      setBatchInfo(sessionAdapter.getSummary())
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '新图数量检查失败')
    }
  }, [sessionAdapter])

  /** 显式换批：放弃当前 ACTIVE 会话 → 按 mode 新建冻结队列 → 重新加载第 1 页。 */
  const switchBatch = useCallback(
    async (mode: ReviewBatchMode): Promise<void> => {
      if (!loader || switching) return
      const seq = ++batchSeqRef.current
      setSwitching(true)
      setError(null)
      try {
        if (sessionAdapter) await sessionAdapter.startNextBatch(mode)
        const page = await loader.loadPage(1)
        if (seq !== batchSeqRef.current) return
        loadedPageRef.current = page.startPage ?? 1
        setList(page.items)
        setHasNext(page.has_next)
        setServerTotal(page.total)
        setIndex(page.initialIndex ?? 0)
        setFinished(false)
        setZoomed(false)
        setSessionKept(0)
        setSessionRejected(0)
        setSessionFavorited(0)
        undoRef.current = []
        refreshStats()
        if (sessionAdapter) {
          setBatchInfo(sessionAdapter.getSummary())
          setNewCount(await sessionAdapter.countOutsideBatch())
        }
      } catch (err) {
        if (seq === batchSeqRef.current) {
          setError(err instanceof ApiRequestError ? err.message : '切换审核批次失败')
        }
      } finally {
        if (seq === batchSeqRef.current) setSwitching(false)
      }
    },
    [loader, sessionAdapter, switching, refreshStats],
  )

  // 分页模式：首屏加载第一页
  useEffect(() => {
    if (!loader) return
    let cancelled = false
    setLoadingMore(true)
    loader
      .loadPage(1)
      .then((page) => {
        if (cancelled) return
        loadedPageRef.current = page.startPage ?? 1
        setList(page.items)
        setHasNext(page.has_next)
        setServerTotal(page.total)
        setIndex(page.initialIndex ?? 0)
        setBatchInfo(sessionAdapter?.getSummary() ?? null)
        void checkNewCount()
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : '加载审核列表失败')
      })
      .finally(() => {
        if (!cancelled) setLoadingMore(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const clamped = Math.min(Math.max(index, 0), Math.max(list.length - 1, 0))
  const current = list[clamped]

  // 接近末尾时预取下一页（去重 append）
  const maybePrefetch = useCallback(() => {
    if (!loader || !hasNext || loadingMore) return
    if (clamped < list.length - 3) return
    const seq = ++prefetchSeqRef.current
    setLoadingMore(true)
    loader
      .loadPage(loadedPageRef.current + 1)
      .then((page) => {
        if (seq !== prefetchSeqRef.current) return
        loadedPageRef.current += 1
        setHasNext(page.has_next)
        setServerTotal(page.total)
        setList((prev) => {
          const known = new Set(prev.map((img) => img.id))
          const fresh = page.items.filter((img) => !known.has(img.id))
          return [...prev, ...fresh]
        })
      })
      .catch((err: unknown) => setError(err instanceof ApiRequestError ? err.message : '加载下一页失败'))
      .finally(() => {
        if (seq === prefetchSeqRef.current) setLoadingMore(false)
      })
  }, [loader, hasNext, loadingMore, clamped, list.length])

  useEffect(() => {
    maybePrefetch()
  }, [maybePrefetch])

  const goTo = useCallback(
    (next: number) => {
      if (next < 0) return
      // 在末尾再按"下一张"且无下一页 → 进入结束态
      if (next >= list.length) {
        if (!hasNext) {
          setZoomed(false)
          setFinished(true)
        }
        return
      }
      setZoomed(false)
      indexRef.current = next
      setIndex(next)
    },
    [list.length, hasNext],
  )

  // 打标请求队列：用户快速连按 A/D 时，PATCH 期间的按键排队、逐张落标并自动前进。
  const listRef = useRef<ImageDTO[]>(list)
  listRef.current = list
  const indexRef = useRef<number>(clamped)
  indexRef.current = clamped
  const queueRef = useRef<ImageReviewStatus[]>([])
  const processingRef = useRef(false)

  const applyUpdated = useCallback(
    (updated: ImageDTO) => {
      setList((prev) => prev.map((img) => (img.id === updated.id ? updated : img)))
      onChanged?.(updated)
    },
    [onChanged],
  )

  // Phase 0.13：打标/收藏决策通道。有 sessionAdapter → 冻结会话单事务 decision（带乐观锁）；
  // 否则回落旧 imageApi（静态集合模式行为不变）。
  const decide = useCallback(
    (image: ImageDTO, action: ImageReviewStatus): Promise<ImageDTO> => {
      if (sessionAdapter) return sessionAdapter.decideMark(image as SessionImage, action)
      return imageApi.setStatus(image.id, { status: action })
    },
    [sessionAdapter],
  )

  const favoriteImage = useCallback(
    (image: ImageDTO, next: boolean): Promise<ImageDTO> => {
      if (sessionAdapter) return sessionAdapter.setFavorite(image as SessionImage, next)
      return imageApi.favorite(image.id, next)
    },
    [sessionAdapter],
  )

  // 409 REVIEW_CONFLICT：按权威 Image 刷新当前项（错误体带 image 用之；否则 GET 单图兜底），不前进。
  const resyncConflict = useCallback(
    async (cur: ImageDTO, err: unknown): Promise<void> => {
      if (!sessionAdapter) return
      try {
        const authoritative = await sessionAdapter.resync(
          cur as SessionImage,
          conflictAuthoritativeImage(err),
        )
        applyUpdated(authoritative)
      } catch {
        // 同步失败保留原错误提示即可
      }
    },
    [sessionAdapter, applyUpdated],
  )

  const processQueue = useCallback(async () => {
    if (processingRef.current) return
    processingRef.current = true
    setBusy(true)
    try {
      while (queueRef.current.length > 0) {
        const curIndex = indexRef.current
        const cur = listRef.current[curIndex]
        if (!cur) break
        const status = queueRef.current.shift() as ImageReviewStatus
        try {
          // 记录 undo（打标前快照）
          undoRef.current.push({
            image: cur,
            prevStatus: normalizeImageStatus(cur),
            prevFavorite: cur.favorite,
          })
          if (undoRef.current.length > 50) undoRef.current.shift()
          const updated = await decide(cur, status)
          applyUpdated(updated)
          if (status === 'KEEP') setSessionKept((n) => n + 1)
          else if (status === 'REJECT') setSessionRejected((n) => n + 1)
          refreshStats()
        } catch (err) {
          if (err instanceof ApiRequestError && err.code === 'REVIEW_CONFLICT' && sessionAdapter) {
            await resyncConflict(cur, err)
            setError('图片状态已在他处修改，已按最新状态同步，本次未计入打标')
          } else {
            setError(err instanceof ApiRequestError ? err.message : '审核状态更新失败')
          }
          break // 出错即停，把队列留给用户看到错误后决定
        }
        // 打标后自动跳到下一张（到末尾则停住）
        if (curIndex < listRef.current.length - 1) {
          indexRef.current = curIndex + 1
          setIndex(curIndex + 1)
        }
      }
    } finally {
      processingRef.current = false
      setBusy(false)
    }
  }, [applyUpdated, decide, refreshStats, resyncConflict, sessionAdapter])

  const enqueueMark = useCallback(
    (status: ImageReviewStatus) => {
      setError(null)
      queueRef.current.push(status)
      void processQueue()
    },
    [processQueue],
  )

  // 收藏：独立 toggle favorite，不改审核状态
  const toggleFavorite = useCallback(async () => {
    const cur = listRef.current[indexRef.current]
    if (!cur) return
    setError(null)
    try {
      undoRef.current.push({
        image: cur,
        prevStatus: normalizeImageStatus(cur),
        prevFavorite: cur.favorite,
      })
      if (undoRef.current.length > 50) undoRef.current.shift()
      const updated = await favoriteImage(cur, !cur.favorite)
      applyUpdated(updated)
      setSessionFavorited((n) => n + 1)
      refreshStats()
    } catch (err) {
      if (err instanceof ApiRequestError && err.code === 'REVIEW_CONFLICT' && sessionAdapter) {
        await resyncConflict(cur, err)
        setError('图片状态已在他处修改，已按最新状态同步，本次未计入收藏')
      } else {
        setError(err instanceof ApiRequestError ? err.message : '收藏更新失败')
      }
    }
  }, [applyUpdated, favoriteImage, refreshStats, resyncConflict, sessionAdapter])

  // Phase 0.12：Ctrl+Z 撤销上一条（恢复打标/收藏前快照）
  const undoLast = useCallback(async () => {
    const entry = undoRef.current.pop()
    if (!entry) return
    setError(null)
    try {
      // 乐观锁 expected 取列表里最新权威值（打标后已被响应替换），不能用打标前快照
      const current = listRef.current.find((img) => img.id === entry.image.id) ?? entry.image
      const reverted = await decide(current, entry.prevStatus)
      applyUpdated(reverted)
      if (entry.prevFavorite !== reverted.favorite) {
        applyUpdated(await favoriteImage(reverted, entry.prevFavorite))
      }
      refreshStats()
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '撤销失败')
    }
  }, [applyUpdated, decide, favoriteImage, refreshStats])

  // 键盘：←/→ 切换；A 保留 / D 淘汰 / F 收藏；Space 放大；Ctrl+Z 撤销；ESC 关闭
  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      const tag = (event.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
        event.preventDefault()
        void undoLast()
        return
      }
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault()
        goTo(clamped - 1)
      } else if (event.key === 'ArrowRight') {
        event.preventDefault()
        goTo(clamped + 1)
      } else if (event.key === ' ' || event.code === 'Space') {
        event.preventDefault()
        setZoomed((z) => !z)
      } else if (event.key === 'a' || event.key === 'A') {
        event.preventDefault()
        enqueueMark('KEEP')
      } else if (event.key === 'd' || event.key === 'D') {
        event.preventDefault()
        enqueueMark('REJECT')
      } else if (event.key === 'f' || event.key === 'F') {
        event.preventDefault()
        void toggleFavorite()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [clamped, goTo, enqueueMark, toggleFavorite, undoLast, onClose])

  // 打开期间锁定 body 滚动
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [])

  // Phase 0.13：断点续看——浏览位置变化时上报 session（fire-and-forget）
  useEffect(() => {
    if (!sessionAdapter) return
    const cur = listRef.current[indexRef.current]
    if (cur) sessionAdapter.reportPosition(cur as SessionImage)
  }, [clamped, list, sessionAdapter])

  // Phase 0.13 / v0.37：进入结束态时标记会话完成（仍有未审由后端不强完成）；
  // 完成后立即按该会话统计批次之外的新图，供“审新一批”入口使用。
  const isComplete = finished && !loadingMore
  useEffect(() => {
    if (!isComplete || !sessionAdapter) return
    let cancelled = false
    sessionAdapter
      .finish()
      .then(() => {
        if (cancelled) return
        setBatchInfo(sessionAdapter.getSummary())
        return checkNewCount()
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiRequestError ? err.message : '标记审核完成失败')
        }
      })
    return () => {
      cancelled = true
    }
  }, [isComplete, sessionAdapter, checkNewCount])

  if (list.length === 0 || !current) {
    const ended = batchInfo?.status === 'COMPLETED'
    return (
      <div className="rv-overlay" role="dialog" aria-modal="true" aria-label="审核模式">
        <div className="rv-top">
          <span className="rv-progress">
            {loadingMore ? '加载中…' : ended ? '上一批审核已结束' : '没有可审核的图片'}
          </span>
          <button type="button" onClick={onClose}>关闭</button>
        </div>
        {error && <p className="rv-error">{error}</p>}
        <div className="rv-done">
          <h2 className="rv-done__title">{ended ? '上一批审核已结束' : '暂无待审核图片'}</h2>
          <p className="rv-done__remaining muted">
            {newCount === null
              ? '正在检查新图…'
              : newCount > 0
                ? `批次之外还有 ${newCount} 张待审核图片`
                : '当前没有新的待审核图片'}
          </p>
          <div className="rv-done__actions">
            {newCount !== null && newCount > 0 && (
              <button
                type="button" className="rv-btn rv-btn--keep" disabled={switching}
                onClick={() => void switchBatch('only_new')}
              >
                {switching ? '切换中…' : `审新图（${newCount} 张）`}
              </button>
            )}
            <button
              type="button" className="rv-btn rv-btn--secondary" disabled={switching}
              onClick={() => void switchBatch('all')}
            >
              审核全部未审核
            </button>
            <button type="button" className="rv-btn" disabled={switching} onClick={() => void checkNewCount()}>
              检查新图
            </button>
            <button type="button" className="rv-btn" onClick={onClose}>返回图库</button>
          </div>
        </div>
      </div>
    )
  }

  // Phase 0.12：结束态——队列耗尽
  if (isComplete) {
    return (
      <div className="rv-overlay rv-overlay--done" role="dialog" aria-modal="true" aria-label="审核完成">
        <div className="rv-top">
          <span className="rv-progress">本次审核完成{title ? ` · ${title}` : ''}</span>
          <button type="button" onClick={onClose}>返回图库</button>
        </div>
        <div className="rv-done">
          <h2 className="rv-done__title">本次审核完成</h2>
          <p className="rv-done__counts">
            保留 <strong>{sessionKept}</strong> · 淘汰 <strong>{sessionRejected}</strong> · 收藏 <strong>{sessionFavorited}</strong>
          </p>
          {serverStats && (
            <p className="rv-done__remaining muted">剩余待审（全局）{serverStats.new} 张</p>
          )}
          <div className="rv-done__actions">
            <button type="button" className="rv-btn rv-btn--keep" onClick={onClose}>返回图库</button>
            {loader && (
              <>
                <button
                  type="button" className="rv-btn rv-btn--secondary" disabled={switching}
                  onClick={() => void switchBatch('only_new')}
                >
                  {switching
                    ? '切换中…'
                    : newCount !== null && newCount > 0
                      ? `审新一批（仅新图 ${newCount} 张）`
                      : '审新一批（仅新图）'}
                </button>
                <button
                  type="button" className="rv-btn" disabled={switching}
                  onClick={() => void switchBatch('all')}
                >
                  审核全部未审核
                </button>
                <button type="button" className="rv-btn" disabled={switching} onClick={() => void checkNewCount()}>
                  刷新新图数量
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    )
  }

  const denom = serverTotal ?? list.length
  const imgSrc = zoomed ? imageContentUrl(current.id) : imagePreviewUrl(current.id)

  return (
    <div className="rv-overlay" role="dialog" aria-modal="true" aria-label="审核模式">
      <div className="rv-top">
        <span className="rv-progress" aria-live="polite">
          {clamped + 1} / {denom}{title ? ` · ${title}` : ''}
          {loadingMore && ' · 加载更多…'}
        </span>
        <span className="rv-stats muted">
          {serverStats
            ? `剩余待审 ${serverStats.new} · 全局 保留 ${serverStats.keep} · 淘汰 ${serverStats.reject} · 收藏 ${serverStats.favorites}`
            : `本次 保留 ${sessionKept} · 淘汰 ${sessionRejected} · 收藏 ${sessionFavorited}`}
        </span>
        {sessionAdapter && (
          <span className="rv-new muted">
            {newCount === null
              ? '新图检查中…'
              : newCount > 0
                ? `另有 ${newCount} 张未纳入本批`
                : '暂无新图'}
            <button type="button" className="rv-link" disabled={switching} onClick={() => void checkNewCount()}>
              检查
            </button>
            {newCount !== null && newCount > 0 && (
              <button
                type="button" className="rv-link" disabled={switching}
                onClick={() => void switchBatch('only_new')}
              >
                换批审新图
              </button>
            )}
          </span>
        )}
        <button type="button" onClick={onClose}>退出审核</button>
      </div>

      {error && <p className="rv-error">{error}</p>}

      <div className="rv-stage">
        <button
          type="button" className="rv-nav rv-nav--left"
          disabled={clamped <= 0}
          onClick={() => goTo(clamped - 1)}
          aria-label="上一张"
        >
          ‹
        </button>
        <img
          className={`rv-img${zoomed ? ' rv-img--zoomed' : ''}`}
          src={imgSrc}
          alt=""
          onClick={() => setZoomed((z) => !z)}
        />
        <button
          type="button" className="rv-nav rv-nav--right"
          disabled={clamped >= list.length - 1}
          onClick={() => goTo(clamped + 1)}
          aria-label="下一张"
        >
          ›
        </button>
      </div>

      <div className="rv-toolbar">
        <span className="muted">快捷键：← → 切换 · A 保留 · D 淘汰 · F 收藏 · Space 放大 · Ctrl+Z 撤销</span>
        <div className="rv-actions">
          <button
            type="button" className="rv-btn rv-btn--reject" disabled={busy}
            onClick={() => enqueueMark('REJECT')}
          >
            ❌ 淘汰 (D)
          </button>
          <button
            type="button" className="rv-btn rv-btn--keep" disabled={busy}
            onClick={() => enqueueMark('KEEP')}
          >
            ✅ 保留 (A)
          </button>
          <button
            type="button" className="rv-btn rv-btn--fav"
            onClick={() => void toggleFavorite()}
          >
            {current.favorite ? '★ 已收藏 (F)' : '⭐ 收藏 (F)'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default ReviewMode
