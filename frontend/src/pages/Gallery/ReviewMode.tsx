import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiRequestError, imageApi } from '../../api/client'
import {
  imageContentUrl,
  normalizeImageStatus,
  type ImageDTO,
  type ImageReviewStatus,
} from '../../types/workbench'
import './review-mode.css'

/**
 * Phase 0.11 摄影选片式 Review Mode（全屏）。
 *
 * - 居中大图（载 original content）+ ←/→ 切换 + ✅保留 / ⭐收藏 / ❌淘汰；
 * - 快捷键：← 上一张、→ 下一张、A 保留、D 淘汰、F 收藏、Space 放大、ESC 关闭；
 * - 打标后自动跳到下一张；顶部显示进度（如 3 / 16）与 保留/收藏/淘汰/待审 统计。
 *
 * 只在现有 ImageDTO / imageApi.setStatus 之上扩展，不触碰 Lightbox 本体。
 */
export interface ReviewModeProps {
  images: ImageDTO[]
  initialIndex?: number
  title?: string
  onClose: () => void
  /** 单张打标后同步回 Gallery 列表（保持 Grid 徽标一致） */
  onChanged?: (image: ImageDTO) => void
}

export function ReviewMode({ images, initialIndex = 0, title, onClose, onChanged }: ReviewModeProps) {
  const [list, setList] = useState<ImageDTO[]>(images)
  const [index, setIndex] = useState(() => Math.min(Math.max(initialIndex, 0), Math.max(images.length - 1, 0)))
  const [zoomed, setZoomed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const clamped = Math.min(Math.max(index, 0), Math.max(list.length - 1, 0))
  const current = list[clamped]

  const stats = useMemo(() => {
    const s = { NEW: 0, KEEP: 0, FAVORITE: 0, REJECT: 0, ARCHIVED: 0 }
    for (const img of list) s[normalizeImageStatus(img)] += 1
    return s
  }, [list])

  const goTo = useCallback(
    (next: number) => {
      if (next < 0 || next >= list.length) return
      setZoomed(false)
      indexRef.current = next
      setIndex(next)
    },
    [list.length],
  )

  // 打标请求队列：用户快速连按 A/D/F 时，PATCH 期间的按键不再被丢弃，
  // 而是排队、逐张落标并自动前进（摄影选片场景的关键健壮性）。
  const listRef = useRef<ImageDTO[]>(list)
  listRef.current = list
  const indexRef = useRef<number>(clamped)
  indexRef.current = clamped
  const queueRef = useRef<ImageReviewStatus[]>([])
  const processingRef = useRef(false)

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
          setList((prev) => prev.map((img) => (img.id === cur.id ? updated : img)))
          onChanged?.(updated)
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
  }, [onChanged])

  const enqueueMark = useCallback(
    (status: ImageReviewStatus) => {
      setError(null)
      queueRef.current.push(status)
      void processQueue()
    },
    [processQueue],
  )

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
        enqueueMark('FAVORITE')
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [clamped, goTo, enqueueMark, onClose])

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
          <span className="rv-progress">没有可审核的图片</span>
          <button type="button" onClick={onClose}>关闭</button>
        </div>
      </div>
    )
  }

  return (
    <div className="rv-overlay" role="dialog" aria-modal="true" aria-label="审核模式">
      <div className="rv-top">
        <span className="rv-progress" aria-live="polite">
          {clamped + 1} / {list.length}{title ? ` · ${title}` : ''}
        </span>
        <span className="rv-stats muted">
          待审 {stats.NEW} · 保留 {stats.KEEP} · 收藏 {stats.FAVORITE} · 淘汰 {stats.REJECT}
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
          src={imageContentUrl(current.id)}
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
            type="button" className="rv-btn rv-btn--fav" disabled={busy}
            onClick={() => enqueueMark('FAVORITE')}
          >
            ⭐ 收藏 (F)
          </button>
        </div>
      </div>
    </div>
  )
}

export default ReviewMode
