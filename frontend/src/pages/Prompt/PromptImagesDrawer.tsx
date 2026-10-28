import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiRequestError, promptApi } from '../../api/client'
import { Modal } from '../../components/ui/Modal'
import { Badge } from '../../components/ui/Badge'
import {
  IMAGE_STATUS_LABEL,
  type ImageReviewStatus,
  type PromptImageDTO,
} from '../../types/workbench'

/**
 * v0.37 P1-A：Prompt 全部关联图片抽屉。
 *
 * - 卡片仍只预载 3 张缩略图；这里按服务端 offset/limit 分页取全部（每页 40）。
 * - 类型（原图/高清/处理）与审核状态筛选下发服务端，total 与翻页口径一致。
 * - 关闭后再打开复用上次已加载分页（按 prompt + 筛选缓存），不重新全量拉取。
 * - 空态明确；加载失败给出重试，不静默隐藏。
 */

const PAGE_SIZE = 40
const KIND_OPTIONS: Array<{ value: '' | 'original' | 'upscaled' | 'processed'; label: string }> = [
  { value: '', label: '类型：全部' },
  { value: 'original', label: '原图' },
  { value: 'upscaled', label: '高清' },
  { value: 'processed', label: '处理' },
]
const STATUS_OPTIONS: Array<{ value: '' | ImageReviewStatus; label: string }> = [
  { value: '', label: '状态：全部' },
  { value: 'NEW', label: IMAGE_STATUS_LABEL.NEW },
  { value: 'KEEP', label: IMAGE_STATUS_LABEL.KEEP },
  { value: 'REJECT', label: IMAGE_STATUS_LABEL.REJECT },
  { value: 'ARCHIVED', label: IMAGE_STATUS_LABEL.ARCHIVED },
]

type KindFilter = (typeof KIND_OPTIONS)[number]['value']
type StatusFilter = (typeof STATUS_OPTIONS)[number]['value']

/** 已加载分页缓存：关闭抽屉不清空，重开同一筛选直接复用。 */
interface CachedPages {
  items: PromptImageDTO[]
  total: number
  hasMore: boolean
}
const pageCache = new Map<string, CachedPages>()

function cacheKey(promptId: string, kind: KindFilter, status: StatusFilter): string {
  return `${promptId}|${kind}|${status}`
}

export interface PromptImagesDrawerProps {
  promptId: string
  promptName: string
  /** 关闭时回传实际总数，卡片上的 +N 保持同步。 */
  onClose: (total?: number) => void
}

export function PromptImagesDrawer({ promptId, promptName, onClose }: PromptImagesDrawerProps) {
  const [kind, setKind] = useState<KindFilter>('')
  const [status, setStatus] = useState<StatusFilter>('')
  const [items, setItems] = useState<PromptImageDTO[]>([])
  const [total, setTotal] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<PromptImageDTO | null>(null)
  const seqRef = useRef(0)
  const key = cacheKey(promptId, kind, status)

  const fetchPage = useCallback(
    (offset: number) =>
      promptApi.listImages(promptId, {
        limit: PAGE_SIZE,
        offset,
        ...(kind ? { kind } : {}),
        ...(status ? { status } : {}),
      }),
    [promptId, kind, status],
  )

  // 首屏 / 筛选变化：有缓存直接用（不重新请求），否则拉第一页。
  useEffect(() => {
    const cached = pageCache.get(key)
    if (cached) {
      setItems(cached.items)
      setTotal(cached.total)
      setHasMore(cached.hasMore)
      setLoading(false)
      setError(null)
      return
    }
    const seq = ++seqRef.current
    setLoading(true)
    setError(null)
    setItems([])
    setTotal(0)
    fetchPage(0)
      .then((res) => {
        if (seq !== seqRef.current) return
        const has = res.items.length < res.total
        setItems(res.items)
        setTotal(res.total)
        setHasMore(has)
        pageCache.set(key, { items: res.items, total: res.total, hasMore: has })
      })
      .catch((err: unknown) => {
        if (seq === seqRef.current) {
          setError(err instanceof ApiRequestError ? err.message : '加载关联图片失败')
        }
      })
      .finally(() => {
        if (seq === seqRef.current) setLoading(false)
      })
  }, [key, fetchPage])

  async function loadMore(): Promise<void> {
    if (loadingMore) return
    const seq = ++seqRef.current
    setLoadingMore(true)
    setError(null)
    try {
      const res = await fetchPage(items.length)
      if (seq !== seqRef.current) return
      // 去重：同一图片不会因翻页边界重复出现
      const seen = new Set(items.map((it) => it.id))
      const next = [...items, ...res.items.filter((it) => !seen.has(it.id))]
      const has = next.length < res.total
      setItems(next)
      setTotal(res.total)
      setHasMore(has)
      pageCache.set(key, { items: next, total: res.total, hasMore: has })
    } catch (err) {
      if (seq === seqRef.current) {
        setError(err instanceof ApiRequestError ? err.message : '加载更多失败')
      }
    } finally {
      if (seq === seqRef.current) setLoadingMore(false)
    }
  }

  return (
    <Modal
      open
      size="lg"
      title={`${promptName} · 全部关联图片`}
      onClose={() => onClose(total || undefined)}
      footer={
        <div className="pp-imgdrawer__foot">
          <span className="muted">
            已加载 {items.length} / 共 {total} 张
          </span>
          {hasMore && (
            <button
              type="button"
              className="ds-btn ds-btn--secondary ds-btn--md"
              disabled={loadingMore}
              onClick={() => void loadMore()}
            >
              {loadingMore ? '加载中…' : '加载更多'}
            </button>
          )}
        </div>
      }
    >
      <div className="pp-imgdrawer">
        <div className="pp-imgdrawer__filters">
          <select
            aria-label="图片类型"
            value={kind}
            onChange={(e) => setKind(e.target.value as KindFilter)}
          >
            {KIND_OPTIONS.map((opt) => (
              <option key={opt.value || 'all'} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <select
            aria-label="审核状态"
            value={status}
            onChange={(e) => setStatus(e.target.value as StatusFilter)}
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value || 'all'} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <Badge tone="accent">共 {total} 张</Badge>
        </div>

        {selected && (
          <div className="pp-imgdrawer__preview">
            <img src={selected.preview_url} alt="" />
            <div className="pp-imgdrawer__preview-meta muted">
              {selected.width}×{selected.height} · {selected.job_status}
              <button type="button" className="pp-card__action" onClick={() => setSelected(null)}>
                收起
              </button>
            </div>
          </div>
        )}

        {error && (
          <p className="ds-notice ds-notice--error" role="alert">
            {error}
          </p>
        )}

        {loading ? (
          <p className="muted">加载中…</p>
        ) : items.length === 0 ? (
          <p className="muted">该 Prompt 暂无关联图片。</p>
        ) : (
          <div className="pp-imgdrawer__grid">
            {items.map((image) => (
              <button
                key={image.id}
                type="button"
                className="pp-imgdrawer__thumb"
                onClick={() => setSelected(image)}
                title={`${image.width}×${image.height} · ${image.job_status}`}
              >
                <img src={image.thumbnail_url} loading="lazy" decoding="async" alt="" />
              </button>
            ))}
          </div>
        )}
      </div>
    </Modal>
  )
}
