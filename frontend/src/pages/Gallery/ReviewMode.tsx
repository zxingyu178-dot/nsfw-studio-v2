import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiRequestError, imageApi } from '../../api/client'
import {
  imageContentUrl,
  imagePreviewUrl,
  normalizeImageStatus,
  type ImageDTO,
  type ImageReviewStatus,
} from '../../types/workbench'
import './review-mode.css'

/**
 * Phase 0.11.1 摄影选片式 Review Mode（全屏）。
 *
 * - 居中大图 + ←/→ 切换 + ✅保留 / ⭐收藏 / ❌淘汰；
 * - 快捷键：← 上一张、→ 下一张、A 保留、D 淘汰、F 收藏、Space 放大、ESC 关闭；
 * - 打标后自动跳到下一张；顶部显示进度与 待审/保留/淘汰/收藏 统计。
 *
 * 两种数据来源：
 * - static：传入固定 images（兼容旧调用 / 小集合）；
 * - paged：传入 loader，首屏一页、接近末尾预取下一页，直到 has_next=false（全历史审核）。
 *
 * 语义：保留=status KEEP；淘汰=status REJECT；收藏=独立 favorite toggle（不改审核状态）。
 * 渐进加载：默认载 preview，Space 放大时才载 original content。
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
  initialIndex?: number
  title?: string
  onClose: () => void
  /** 单张打标后同步回 Gallery 列表（保持 Grid 徽标一致） */
  onChanged?: (image: ImageDTO) => void
}

interface Stats {
  NEW: number
  KEEP: number
  REJECT: number
  ARCHIVED: number
  favorite: number
}

export function ReviewMode({ images, loader, total, initialIndex = 0, title, onClose, onChanged }: ReviewModeProps) {
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

  const loadedPageRef = useRef(0)
  const prefetchSeqRef = useRef(0)

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

  const stats: Stats = useMemo(() => {
    const s: Stats = { NEW: 0, KEEP: 0, REJECT: 0, ARCHIVED: 0, favorite: 0 }
    for (const img of list) {
      s[normalizeImageStatus(img)] += 1
      if (img.favorite) s.favorite += 1
    }
    return s
  }, [list])

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
      if (next < 0 || next >= list.length) return
      setZoomed(false)
      indexRef.current = next
      setIndex(next)
    },
    [list.length],
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
          const updated = await imageApi.setStatus(cur.id, { status })
          applyUpdated(updated)
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
  }, [applyUpdated])

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
      const updated = await imageApi.favorite(cur.id, !cur.favorite)
      applyUpdated(updated)
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '收藏更新失败')
    }
  }, [applyUpdated])

  // 键盘：←/→ 切换；A 保留 / D 淘汰 / F 收藏；Space 放大；ESC 关闭
  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      const tag = (event.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
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
  }, [clamped, goTo, enqueueMark, toggleFavorite, onClose])

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
          待审 {stats.NEW} · 保留 {stats.KEEP} · 淘汰 {stats.REJECT} · 收藏 {stats.favorite}
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
        <span className="muted">快捷键：← → 切换 · A 保留 · D 淘汰 · F 收藏 · Space 放大</span>
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
