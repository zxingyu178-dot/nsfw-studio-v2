import { Badge } from '../../components/ui'
import {
  ASSET_TYPE_LABEL,
  assetPreviewUrl,
  type AssetDTO,
} from '../../types/workbench'

interface AssetCardProps {
  asset: AssetDTO
  onOpen: (assetId: string) => void
}

/** 单个素材卡片：缩略图 / 名称 / 收藏 / 归档 / tags。点击打开详情抽屉。 */
export function AssetCard({ asset, onOpen }: AssetCardProps) {
  return (
    <article className="as-card" onClick={() => onOpen(asset.id)}>
      <div className="as-card__thumb">
        {asset.current_version?.preview_path ? (
          <img src={assetPreviewUrl(asset.id)} alt={asset.name} loading="lazy" />
        ) : (
          <span className="as-placeholder">{ASSET_TYPE_LABEL[asset.type]}</span>
        )}
      </div>
      <div className="as-card__body">
        <h3 className="as-card__title">
          {asset.favorite && <span title="已收藏">★ </span>}
          {asset.name}
          {asset.archived && <Badge>已归档</Badge>}
        </h3>
        <p className="as-card__tags">
          {(asset.current_version?.tags ?? []).slice(0, 3).map((tag) => (
            <Badge key={tag}>{tag}</Badge>
          ))}
        </p>
      </div>
    </article>
  )
}
