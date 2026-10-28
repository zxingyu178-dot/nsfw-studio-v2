import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiRequestError } from '../../api/client'
import type { ListResponse } from '../../types/workbench'

export interface InfiniteListResult<T> {
  items: T[]
  total: number
  hasMore: boolean
  /** 首次/过滤变更后的整屏加载（已有数据时不切骨架屏） */
  initialLoading: boolean
  /** 过滤变化时保留旧列表的轻量刷新中 */
  refreshing: boolean
  /** “加载更多”追加中 */
  loadingMore: boolean
  error: string | null
  /** 重置并从 offset 0 重新拉取（debounce 后调用） */
  reload: () => void
  /** 静默刷新：保留当前列表与滚动位置，成功后再替换 */
  refresh: () => void
  /** 追加下一页 */
  loadMore: () => void
  /** 局部更新一条（收藏/评分等原地生效，不整表重载） */
  updateItem: (id: string, patch: Partial<T> | ((item: T) => T)) => void
}

interface Options<T> {
  pageSize: number
  /** 真正发请求（limit/offset 由 hook 提供）。需在组件内 useCallback 化以稳定引用。 */
  fetcher: (limit: number, offset: number) => Promise<ListResponse<T>>
  /** 过滤依赖变化时防抖重置。 */
  reloadDeps: unknown[]
  debounceMs?: number
  /** 兜底错误文案。 */
  fallbackError?: string
}

/**
 * offset 分页 + “加载更多”的通用列表 hook（替代后端默认 50 / 前端写死 100 的隐形上限）。
 *
 * - 初始 / 过滤变化：防抖后从 offset=0 重置；
 * - 加载更多：以当前已加载条数为 offset 追加；
 * - stale guard：用自增序号丢弃过期响应（快速连续输入 / 切过滤时，旧请求晚返回不得覆盖新列表）。
 */
export function useInfiniteList<T>({
  pageSize,
  fetcher,
  reloadDeps,
  debounceMs = 250,
  fallbackError = '加载失败',
}: Options<T>): InfiniteListResult<T> {
  const [items, setItems] = useState<T[]>([])
  const [total, setTotal] = useState(0)
  const [initialLoading, setInitialLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const seqRef = useRef(0)
  const itemsRef = useRef<T[]>([])
  itemsRef.current = items

  const errorText = (err: unknown): string =>
    err instanceof ApiRequestError ? err.message : fallbackError

  const reload = useCallback(() => {
    const seq = ++seqRef.current
    const hasItems = itemsRef.current.length > 0
    // 已有列表时保留旧内容（轻量 refreshing），不再整屏骨架屏
    if (hasItems) setRefreshing(true)
    else setInitialLoading(true)
    setError(null)
    fetcher(pageSize, 0)
      .then((res) => {
        if (seq !== seqRef.current) return
        setItems(res.items)
        setTotal(res.total)
      })
      .catch((err: unknown) => {
        if (seq !== seqRef.current) return
        setError(errorText(err))
      })
      .finally(() => {
        if (seq !== seqRef.current) return
        setInitialLoading(false)
        setRefreshing(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetcher, pageSize])

  // 防抖重置：过滤条件变化
  useEffect(() => {
    const timer = window.setTimeout(() => reload(), debounceMs)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload, ...reloadDeps])

  const refresh = useCallback(() => reload(), [reload])

  const updateItem = useCallback((id: string, patch: Partial<T> | ((item: T) => T)) => {
    setItems((prev) => prev.map((item) => {
      if ((item as { id?: string }).id !== id) return item
      return typeof patch === 'function'
        ? patch(item)
        : { ...item, ...patch }
    }))
  }, [])

  const loadMore = useCallback(() => {
    if (loadingMore || initialLoading) return
    const seq = seqRef.current
    setLoadingMore(true)
    fetcher(pageSize, items.length)
      .then((res) => {
        if (seq !== seqRef.current) return // 期间已触发 reload，丢弃过期追加
        setItems((prev) => [...prev, ...res.items])
        setTotal(res.total)
      })
      .catch((err: unknown) => {
        if (seq !== seqRef.current) return
        setError(errorText(err))
      })
      .finally(() => {
        if (seq === seqRef.current) setLoadingMore(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetcher, pageSize, items.length, loadingMore, initialLoading])

  return {
    items,
    total,
    hasMore: items.length < total,
    initialLoading,
    refreshing,
    loadingMore,
    error,
    reload,
    refresh,
    loadMore,
    updateItem,
  }
}
