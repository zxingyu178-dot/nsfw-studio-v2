import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiRequestError, imageApi } from '../../../api/client'
import type {
  ImageDTO,
  ImageJobGroupDTO,
  ImageReviewStatus,
  ImageSort,
} from '../../../types/workbench'

/**
 * Phase 0.12 Task9：图库列表查询 hook（从 GalleryPage 抽取，行为不变）。
 *
 * 负责：tab / subStatus / sort 过滤状态、分页 list（无限滚动 + requestSeq 竞态守卫）、
 * 按任务分组聚合分页。ViewMode（flat/group）与 jobFilter 由父组件持有并传入。
 */

export type TabKey = 'ALL' | 'NEW' | 'FAVORITE' | 'ARCHIVED'

export const PAGE_SIZE = 40

export interface GalleryListQuery {
  job_id: string | null | undefined
  sort: ImageSort
  page: number
  page_size: number
  status?: ImageReviewStatus | null
  favorite?: boolean
}

export function useGalleryQuery(jobFilter: string | null | undefined) {
  const [tab, setTab] = useState<TabKey>('ALL')
  const [subStatus, setSubStatus] = useState<'' | ImageReviewStatus>('')
  const [sort, setSort] = useState<ImageSort>('created_desc')

  // —— 分页状态 ——
  const [items, setItems] = useState<ImageDTO[]>([])
  const [total, setTotal] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Phase 0.11.1：按任务分组后端聚合分页
  const [groups, setGroups] = useState<ImageJobGroupDTO[]>([])
  const [groupsLoading, setGroupsLoading] = useState(false)
  const [groupsPage, setGroupsPage] = useState(1)
  const [groupsHasNext, setGroupsHasNext] = useState(false)

  const requestSeq = useRef(0)
  const sentinelRef = useRef<HTMLDivElement | null>(null)

  // Phase 0.11.1：收藏是独立 boolean。「收藏」Tab 用 favorite=true；其余按 status。
  function listQuery(page: number = 1): GalleryListQuery {
    const query: GalleryListQuery = { job_id: jobFilter, sort, page, page_size: PAGE_SIZE }
    if (subStatus) query.status = subStatus
    else if (tab === 'NEW') query.status = 'NEW'
    else if (tab === 'ARCHIVED') query.status = 'ARCHIVED'
    else if (tab === 'FAVORITE') query.favorite = true
    return query
  }

  // 第一页 / 切筛选或排序 → 重置列表
  const loadFirst = useCallback(() => {
    const seq = ++requestSeq.current
    setLoading(true)
    setError(null)
    imageApi
      .list(listQuery())
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

  // 追加下一页（无限滚动）。带请求序号：切 tab/sort/job 后旧 loadNext 响应不得 append；
  // append 前按 image.id 去重。
  const loadNext = useCallback(() => {
    if (loadingMore || loading || !hasNext) return
    const seq = requestSeq.current
    setLoadingMore(true)
    imageApi
      .list(listQuery(Math.floor(items.length / PAGE_SIZE) + 1))
      .then((page) => {
        if (seq !== requestSeq.current) return
        setItems((prev) => {
          const known = new Set(prev.map((img) => img.id))
          const fresh = page.items.filter((img) => !known.has(img.id))
          return [...prev, ...fresh]
        })
        setHasNext(page.has_next)
        setTotal(page.total)
      })
      .catch((err: unknown) => setError(err instanceof ApiRequestError ? err.message : '加载更多失败'))
      .finally(() => {
        if (seq === requestSeq.current) setLoadingMore(false)
      })
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

  const loadGroups = useCallback((page: number) => {
    setGroupsLoading(true)
    imageApi
      .jobGroups({ page, page_size: 20 })
      .then((result) => {
        setGroups((prev) => (page === 1 ? result.items : [...prev, ...result.items]))
        setGroupsPage(page)
        setGroupsHasNext(result.has_next)
      })
      .catch((err: unknown) => setError(err instanceof ApiRequestError ? err.message : '无法加载任务分组'))
      .finally(() => setGroupsLoading(false))
  }, [])

  const resetGroups = useCallback(() => setGroups([]), [])

  // 单张打标/收藏后，同步更新列表中对应图（保持徽标一致）
  const applyItemUpdated = useCallback((updated: ImageDTO) => {
    setItems((previous) => previous.map((item) => (item.id === updated.id ? updated : item)))
  }, [])

  const removeItem = useCallback((imageId: string) => {
    setItems((previous) => previous.filter((item) => item.id !== imageId))
  }, [])

  return {
    // 过滤状态
    tab, setTab,
    subStatus, setSubStatus,
    sort, setSort,
    // 列表
    items, setItems,
    total, hasNext, loading, loadingMore,
    error, setError,
    loadFirst, loadNext,
    sentinelRef, listQuery,
    applyItemUpdated, removeItem,
    // 分组
    groups, groupsLoading, groupsPage, groupsHasNext,
    loadGroups, resetGroups,
  }
}
