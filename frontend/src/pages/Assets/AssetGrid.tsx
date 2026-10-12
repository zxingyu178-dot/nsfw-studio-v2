import type { AssetDTO } from '../../types/workbench'
import { AssetCard } from './AssetCard'

interface AssetGridProps {
  items: AssetDTO[]
  onOpen: (assetId: string) => void
}

/** 素材网格：把素材列表映射为卡片。 */
export function AssetGrid({ items, onOpen }: AssetGridProps) {
  return (
    <div className="as-grid">
      {items.map((asset) => (
        <AssetCard key={asset.id} asset={asset} onOpen={onOpen} />
      ))}
    </div>
  )
}
