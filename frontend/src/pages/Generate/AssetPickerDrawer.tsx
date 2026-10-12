import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiRequestError, assetApi } from '../../api/client'
import { Button, Drawer, Input } from '../../components/ui'
import { ASSET_TYPE_LABEL, assetPreviewUrl, type AssetDTO, type AssetType } from '../../types/workbench'

interface AssetPickerDrawerProps {
  slot: AssetType
  onClose: () => void
  onPicked: (promptText: string, ref: { asset_id: string; asset_version_id: string; name: string }) => void
}

const PAGE_SIZE = 60

/**
 * 工作台内的素材选择 Drawer（规范 §四十五；Phase 0.12 任务 10.5）。
 * 修复隐形上限：旧实现 `limit: 60` 无翻页，第 61 个以后素材选不到。
 * 现在按分页逐页追加（offset 递增），搜索/slot 切换用 stale guard（reqId）丢弃过期响应，
 * 保证快速连续搜索时不会把旧页结果拼进新结果。
 */
export function AssetPickerDrawer({ slot, onClose, onPicked }: AssetPickerDrawerProps) {
  const [items, setItems] = useState<AssetDTO[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasNext, setHasNext] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const offsetRef = useRef(0)
  const reqIdRef = useRef(0)

  const reload = useCallback(
    (searchText: string) => {
      const reqId = ++reqIdRef.current
      offsetRef.current = 0
      setLoading(true)
      setError(null)
      assetApi
        .list({ type: slot, search: searchText || undefined, limit: PAGE_SIZE, offset: 0 })
        .then((page) => {
          if (reqId !== reqIdRef.current) return
          setItems(page.items)
          offsetRef.current = page.items.length
          setHasNext(page.items.length >= PAGE_SIZE)
        })
        .catch((err: unknown) => {
          if (reqId !== reqIdRef.current) return
          setError(err instanceof ApiRequestError ? err.message : '加载素材失败')
        })
        .finally(() => {
          if (reqId === reqIdRef.current) setLoading(false)
        })
    },
    [slot],
  )

  useEffect(() => {
    reload('')
  }, [reload])

  useEffect(() => {
    const timer = window.setTimeout(() => reload(search.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [search, reload])

  function loadMore(): void {
    const reqId = reqIdRef.current
    setLoadingMore(true)
    assetApi
      .list({ type: slot, search: search.trim() || undefined, limit: PAGE_SIZE, offset: offsetRef.current })
      .then((page) => {
        if (reqId !== reqIdRef.current) return
        setItems((prev) => {
          const seen = new Set(prev.map((asset) => asset.id))
          return [...prev, ...page.items.filter((asset) => !seen.has(asset.id))]
        })
        offsetRef.current += page.items.length
        setHasNext(page.items.length >= PAGE_SIZE)
      })
      .catch(() => {
        // 加载下一页失败不阻断当前列表，用户可重试
      })
      .finally(() => {
        if (reqId === reqIdRef.current) setLoadingMore(false)
      })
  }

  return (
    <Drawer open onClose={onClose} title={`选择${ASSET_TYPE_LABEL[slot]}素材`}>
      <Input
        className="wb-asset-search"
        placeholder="搜索素材名称 / Prompt"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />

      {loading && <p className="muted">加载中…</p>}
      {error && <p className="ds-notice ds-notice--error">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="muted">暂无{ASSET_TYPE_LABEL[slot]}素材，可在“素材”页上传。</p>
      )}

      <div className="wb-asset-grid">
        {items.map((asset) => (
          <button
            key={asset.id}
            type="button"
            className="wb-asset-item"
            title={asset.current_version?.prompt_text || asset.name}
            onClick={() => {
              const version = asset.current_version
              onPicked(version?.prompt_text ?? '', {
                asset_id: asset.id,
                asset_version_id: version?.id ?? '',
                name: asset.name,
              })
            }}
          >
            <span className="wb-asset-thumb">
              {asset.current_version?.preview_path ? (
                <img src={assetPreviewUrl(asset.id)} alt={asset.name} />
              ) : (
                <span className="wb-asset-placeholder">{ASSET_TYPE_LABEL[slot]}</span>
              )}
            </span>
            <span className="wb-asset-name">{asset.name}</span>
          </button>
        ))}
      </div>

      {!loading && hasNext && (
        <div className="wb-asset-more">
          <Button size="sm" variant="ghost" disabled={loadingMore} onClick={loadMore}>
            {loadingMore ? '加载中…' : `加载更多（已选 ${items.length}）`}
          </Button>
        </div>
      )}
    </Drawer>
  )
}
