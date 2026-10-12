import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiRequestError, imageApi, type ImageStatsParams } from '../../api/client'
import {
  imageContentUrl,
  imagePreviewUrl,
  normalizeImageStatus,
  type ImageDTO,
  type ImageReviewStatus,
  type ImageStatsResponse,
} from '../../types/workbench'
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
 */

/** 分页加载器：page 从 1 起。返回本页 items + 是否还有下一页 + 服务端 total。 */
export interface ReviewPageLoader {
  loadPage: (page: number) => Promise<{ items: ImageDTO[]; has_next: boolean; total: number }>
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
  initialIndex?: number
  title?: string
  onClose: () => void
  /** 单张打标后同步回 Gallery 列表（保持 Grid 徽标一致） */
  onChanged?: (image: ImageDTO) => void
}

interface UndoEntry {
  imageId: string
  prevStatus: ImageReviewStatus
  prevFavorite: boolean
}

export function ReviewMode({ images, loader, total, statsParams, initialIndex = 0, title, onClose, onChanged }: ReviewModeProps) {
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
  const undoRef = useRef<UndoEntry[]>([])

  const loadedPageRef = useRef(0)
  const prefetchSeqRef = useRef(0)

  const refreshStats = useCallback(() => {
    if (!statsParams || typeof imageApi.stats !== 'function') return
    imageApi
      .stats(statsParams)
      .then((s) => setServerStats(s))
      .catch(() => {})
  }, [statsParams])

  useEffect(() => {
    refreshStats()
  }, [refreshStats])

  // 分页模式：首屏加载第一页
  useEffect(() => {
    if (!loader) return
    let cancelled = false
    setLoadingMore(true)
    loader
      .loadPage(1)
      .then((page) => {
        if (cancelled) return
        loadedPageRef.current = 1
        setList(page.items)
        setHasNext(page.has_next)
        setServerTotal(page.total)
        setIndex(0)
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
            imageId: cur.id,
            prevStatus: normalizeImageStatus(cur),
            prevFavorite: cur.favorite,
          })
          if (undoRef.current.length > 50) undoRef.current.shift()
          const updated = await imageApi.setStatus(cur.id, { status })
          applyUpdated(updated)
          if (status === 'KEEP') setSessionKept((n) => n + 1)
          else if (status === 'REJECT') setSessionRejected((n) => n + 1)
          refreshStats()
        } catch (err) {
          setError(err instanceof ApiRequestError ? err.message : '审核状态更新失败')
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
  }, [applyUpdated, refreshStats])

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
        imageId: cur.id,
        prevStatus: normalizeImageStatus(cur),
        prevFavorite: cur.favorite,
      })
      if (undoRef.current.length > 50) undoRef.current.shift()
      const updated = await imageApi.favorite(cur.id, !cur.favorite)
      applyUpdated(updated)
      setSessionFavorited((n) => n + 1)
      refreshStats()
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '收藏更新失败')
    }
  }, [applyUpdated, refreshStats])

  // Phase 0.12：Ctrl+Z 撤销上一条（恢复打标/收藏前快照）
  const undoLast = useCallback(async () => {
    const entry = undoRef.current.pop()
    if (!entry) return
    setError(null)
    try {
      const reverted = await imageApi.setStatus(entry.imageId, { status: entry.prevStatus })
      applyUpdated(reverted)
      if (entry.prevFavorite !== reverted.favorite) {
        applyUpdated(await imageApi.favorite(entry.imageId, entry.prevFavorite))
      }
      refreshStats()
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '撤销失败')
    }
  }, [applyUpdated, refreshStats])

  // 结束态：用户在末尾再按"下一张"且无下一页
  const isComplete = finished && !loadingMore

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

  if (list.length === 0 || !current) {
    return (
      <div className="rv-overlay" role="dialog" aria-modal="true" aria-label="审核模式">
        <div className="rv-top">
          <span className="rv-progress">{loadingMore ? '加载中…' : '没有可审核的图片'}</span>
          <button type="button" onClick={onClose}>关闭</button>
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
              <button
                type="button"
                className="rv-btn rv-btn--secondary"
                onClick={() => {
                  // 继续审核下一批：重新拉取当前过滤（已打标图已离开过滤集）
                  loadedPageRef.current = 0
                  setIndex(0)
                  setHasNext(true)
                  setZoomed(false)
                  setFinished(false)
                  refreshStats()
                  loader.loadPage(1).then((page) => {
                    loadedPageRef.current = 1
                    setList(page.items)
                    setHasNext(page.has_next)
                    setServerTotal(page.total)
                    setIndex(0)
                  }).catch(() => {})
                }}
              >
                继续审核下一批
              </button>
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
