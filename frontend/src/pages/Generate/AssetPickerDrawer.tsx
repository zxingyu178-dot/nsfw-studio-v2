import { useCallback, useEffect, useState } from 'react'
import { ApiRequestError, assetApi } from '../../api/client'
import { ASSET_TYPE_LABEL, assetPreviewUrl, type AssetDTO, type AssetType } from '../../types/workbench'

interface AssetPickerDrawerProps {
  slot: AssetType
  onClose: () => void
  onPicked: (promptText: string, ref: { asset_id: string; asset_version_id: string; name: string }) => void
}

/** 工作台内的素材选择 Drawer（规范 §四十五）：按 slot 类型列出素材。 */
export function AssetPickerDrawer({ slot, onClose, onPicked }: AssetPickerDrawerProps) {
  const [items, setItems] = useState<AssetDTO[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(
    (searchText: string) => {
      setLoading(true)
      setError(null)
      assetApi
        .list({ type: slot, search: searchText || undefined, limit: 60 })
        .then((page) => setItems(page.items))
        .catch((err: unknown) => {
          setError(err instanceof ApiRequestError ? err.message : '加载素材失败')
        })
        .finally(() => setLoading(false))
    },
    [slot],
  )

  useEffect(() => {
    load('')
  }, [load])

  useEffect(() => {
    const timer = window.setTimeout(() => load(search.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [search, load])

  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`选择${ASSET_TYPE_LABEL[slot]}素材`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drawer__header">
          <h3 className="drawer__title">选择{ASSET_TYPE_LABEL[slot]}素材</h3>
          <button type="button" className="btn btn--ghost btn--sm" onClick={onClose} aria-label="关闭">
            ✕
          </button>
        </header>

        <input
          className="input drawer__search"
          placeholder="搜索素材名称 / Prompt"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />

        {loading && <p className="muted">加载中…</p>}
        {error && <p className="notice notice--error">{error}</p>}
        {!loading && !error && items.length === 0 && (
          <p className="muted">暂无{ASSET_TYPE_LABEL[slot]}素材，可在"素材"页上传。</p>
        )}

        <div className="asset-picker__grid">
          {items.map((asset) => (
            <button
              key={asset.id}
              type="button"
              className="asset-picker__item"
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
              <span className="asset-picker__thumb">
                {asset.current_version?.preview_path ? (
                  <img src={assetPreviewUrl(asset.id)} alt={asset.name} />
                ) : (
                  <span className="asset-thumb-placeholder">{ASSET_TYPE_LABEL[slot]}</span>
                )}
              </span>
              <span className="asset-picker__name">{asset.name}</span>
            </button>
          ))}
        </div>
      </aside>
    </div>
  )
}
