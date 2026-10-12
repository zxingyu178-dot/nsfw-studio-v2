import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiRequestError, imageApi, type ImageListParams } from '../api/client'
import { Drawer, Input, Tabs } from './ui'
import { IMAGE_KIND_LABEL, imageThumbUrl, type ImageDTO } from '../types/workbench'

type PickerFilter = 'RECENT' | 'UNREVIEWED' | 'KEPT' | 'FAVORITE'

const FILTERS: { key: PickerFilter; label: string }[] = [
  { key: 'RECENT', label: '最近' },
  { key: 'UNREVIEWED', label: '未审核' },
  { key: 'KEPT', label: '保留' },
  { key: 'FAVORITE', label: '收藏' },
]

/** 首屏 / 每页大小：禁止一次拉全部，用无限滚动追加直到 has_next=false。 */
const PAGE_SIZE = 40

/**
 * 把 UI 筛选 Tab 映射到后端查询语义（Phase 0.11.1 新审核模型）：
 * - 最近：不带 status，sort=created_desc；
 * - 未审核：status='NEW'；
 * - 保留：status='KEEP'；
 * - 收藏：favorite=true（收藏是独立 boolean，绝不把 status 设成 FAVORITE）。
 */
function buildListParams(filter: PickerFilter, search: string, page: number): ImageListParams {
  const params: ImageListParams = { page, page_size: PAGE_SIZE, sort: 'created_desc' }
  if (filter === 'UNREVIEWED') params.status = 'NEW'
  else if (filter === 'KEPT') params.status = 'KEEP'
  else if (filter === 'FAVORITE') params.favorite = true
  const q = search.trim()
  if (q) params.search = q
  return params
}

/** 按 image.id 去重：以已有列表为准，仅追加新出现的图（防止分页边界重复）。 */
function appendDeduplicated(prev: ImageDTO[], incoming: ImageDTO[]): ImageDTO[] {
  const known = new Set(prev.map((i) => i.id))
  const fresh = incoming.filter((i) => !known.has(i.id))
  return fresh.length ? [...prev, ...fresh] : prev
}

interface ImagePickerDrawerProps {
  title?: string
  onClose: () => void
  onPicked: (image: ImageDTO) => void
}

/** 图库图片选择器（§二十一 / Phase 0.11.1）：
 *  - 标准分页 + IntersectionObserver 哨兵无限滚动（首屏 page=1/page_size=40，到底追加下一页）；
 *  - 网格卡片用 512 WebP 缩略图（imageThumbUrl），只展示尺寸 + 收藏 ★；
 *  - 筛选映射新审核状态；收藏独立；
 *  - 切换筛选 / 搜索自增 request generation，旧请求晚返回直接丢弃，不污染新列表。
 */
export function ImagePickerDrawer({ title = '从图库选择图片', onClose, onPicked }: ImagePickerDrawerProps) {
  const [filter, setFilter] = useState<PickerFilter>('RECENT')
  const [search, setSearch] = useState('')
  const [items, setItems] = useState<ImageDTO[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasNext, setHasNext] = useState(false)

  // 用 ref 保存最新的筛选 / 搜索 / 分页游标 / generation，供哨兵回调（只注册一次）读取。
  const filterRef = useRef(filter)
  filterRef.current = filter
  const searchRef = useRef(search)
  searchRef.current = search
  const generationRef = useRef(0)
  const pageRef = useRef(1)
  const hasNextRef = useRef(false)
  const loadingMoreRef = useRef(false)
  const sentinelRef = useRef<HTMLDivElement | null>(null)

  /** 哨兵触发：追加下一页。受 generation 守卫，旧筛选的在途请求返回会被忽略。 */
  const startLoadMore = useCallback(() => {
    if (loadingMoreRef.current || !hasNextRef.current) return
    const gen = generationRef.current
    const nextPage = pageRef.current + 1
    loadingMoreRef.current = true
    setLoadingMore(true)
    imageApi
      .list(buildListParams(filterRef.current, searchRef.current, nextPage))
      .then((page) => {
        if (gen !== generationRef.current) return
        setItems((prev) => appendDeduplicated(prev, page.items))
        pageRef.current = page.page
        hasNextRef.current = page.has_next
        setHasNext(page.has_next)
      })
      .catch((err: unknown) => {
        if (gen !== generationRef.current) return
        setError(err instanceof ApiRequestError ? err.message : '加载更多图片失败')
      })
      .finally(() => {
        if (gen === generationRef.current) {
          loadingMoreRef.current = false
          setLoadingMore(false)
        }
      })
  }, [])

  // 切换筛选 / 搜索（保留 200ms debounce）：自增 generation 作废在途旧请求，重置到第 1 页。
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const gen = ++generationRef.current
      pageRef.current = 1
      hasNextRef.current = false
      loadingMoreRef.current = false
      setItems([])
      setError(null)
      setHasNext(false)
      setLoadingMore(false)
      setLoading(true)
      imageApi
        .list(buildListParams(filter, search, 1))
        .then((page) => {
          if (gen !== generationRef.current) return
          setItems(appendDeduplicated([], page.items))
          pageRef.current = page.page
          hasNextRef.current = page.has_next
          setHasNext(page.has_next)
        })
        .catch((err: unknown) => {
          if (gen !== generationRef.current) return
          setError(err instanceof ApiRequestError ? err.message : '加载图片失败')
        })
        .finally(() => {
          if (gen === generationRef.current) setLoading(false)
        })
    }, 200)
    return () => window.clearTimeout(timer)
  }, [filter, search])

  // 注册底部哨兵：进入视口即追加下一页（只注册一次，行为读 ref）。
  useEffect(() => {
    const node = sentinelRef.current
    if (!node) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) startLoadMore()
      },
      { rootMargin: '200px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [startLoadMore])

  return (
    <Drawer open onClose={onClose} title={title} width="wide">
      <Tabs
        ariaLabel="图片筛选"
        active={filter}
        onChange={(key) => setFilter(key as PickerFilter)}
        items={FILTERS.map(({ key, label }) => ({ key, label }))}
      />

      <Input
        placeholder="搜索导入文件名"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />

      {loading && <p className="muted">加载中…</p>}
      {error && <p className="ds-notice ds-notice--error">{error}</p>}
      {!loading && !error && items.length === 0 && <p className="muted">没有符合条件的图片。</p>}

      <div className="wb-image-grid">
        {items.map((image) => (
          <button
            key={image.id}
            type="button"
            className="wb-image-item"
            title={`${IMAGE_KIND_LABEL[image.kind] ?? image.kind} · ${image.width}×${image.height}`}
            onClick={() => onPicked(image)}
          >
            <img src={imageThumbUrl(image.id)} alt="" loading="lazy" />
            <span className="wb-image-meta">
              {image.width}×{image.height}
              {image.favorite && <span title="已收藏"> ★</span>}
            </span>
          </button>
        ))}
      </div>

      <div ref={sentinelRef} aria-hidden="true" style={{ height: 1 }} />
      {loadingMore && <p className="muted">加载更多…</p>}
      {!hasNext && items.length > 0 && !loading && <p className="muted">已经到底了。</p>}
    </Drawer>
  )
}
