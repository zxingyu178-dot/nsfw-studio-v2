import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiRequestError, assetApi } from '../../api/client'
import { ImagePickerDrawer } from '../../components/ImagePickerDrawer'
import { Badge, Button, Drawer } from '../../components/ui'
import { formatDateTime } from '../../utils/format'
import {
  ASSET_TYPE_LABEL,
  assetPreviewUrl,
  imageContentUrl,
  type AssetDTO,
  type AssetVersionDTO,
} from '../../types/workbench'
import { AssetEditor } from './AssetEditor'

export interface AssetDetailDrawerProps {
  assetId: string
  onClose: () => void
  onUseInWorkbench: () => void
  onError: (message: string) => void
}

/** 素材详情抽屉：预览 / 操作 / 字段 / Face 参考图 / 版本历史 / 编辑器入口。 */
export function AssetDetailDrawer({ assetId, onClose, onUseInWorkbench, onError }: AssetDetailDrawerProps) {
  const [asset, setAsset] = useState<AssetDTO | null>(null)
  const [versions, setVersions] = useState<AssetVersionDTO[]>([])
  const [viewVersion, setViewVersion] = useState<number | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [refPickerOpen, setRefPickerOpen] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const loadRef = useRef<() => void>(() => undefined)

  const load = useCallback(() => {
    Promise.all([assetApi.get(assetId), assetApi.listVersions(assetId)])
      .then(([detail, versionList]) => {
        setAsset(detail)
        setVersions(versionList)
      })
      .catch((err: unknown) => {
        onError(err instanceof ApiRequestError ? err.message : '加载失败')
        onClose()
      })
  }, [assetId, onClose, onError])

  loadRef.current = load
  useEffect(() => {
    loadRef.current()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assetId])

  async function run(action: () => Promise<unknown>, okText: string): Promise<void> {
    setBusy(true)
    setMessage(null)
    try {
      await action()
      load()
      if (okText) setMessage(okText)
    } catch (err) {
      onError(err instanceof ApiRequestError ? err.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  async function bindReference(imageId: string): Promise<void> {
    setRefPickerOpen(false)
    const formData = new FormData()
    formData.set('reference_image_id', imageId)
    formData.set('reference_action', 'set')
    await run(() => assetApi.addVersion(assetId, formData), '已绑定参考图（创建新版本）')
  }

  async function clearReference(): Promise<void> {
    const formData = new FormData()
    formData.set('reference_action', 'clear')
    await run(() => assetApi.addVersion(assetId, formData), '已移除参考图（创建新版本）')
  }

  if (!asset) {
    return (
      <Drawer open onClose={onClose} title="加载中…">
        <p className="muted">加载中…</p>
      </Drawer>
    )
  }

  const shownVersion =
    viewVersion === null
      ? asset.current_version
      : (versions.find((version) => version.version_no === viewVersion) ?? asset.current_version)

  const referenceImageId = shownVersion?.reference_images?.[0] ?? null

  return (
    <Drawer open onClose={onClose} width="wide" title={asset.name}>
      <div className="as-detail__preview">
        {shownVersion?.preview_path ? (
          <img src={assetPreviewUrl(asset.id, viewVersion ?? undefined)} alt={asset.name} />
        ) : (
          <span className="as-placeholder as-placeholder--lg">{ASSET_TYPE_LABEL[asset.type]}</span>
        )}
      </div>

      <div className="as-actions">
        <Button size="sm" variant="primary" onClick={onUseInWorkbench}>用于生成</Button>
        <Button
          size="sm" variant="ghost" disabled={!shownVersion?.prompt_text}
          onClick={() => {
            void navigator.clipboard
              .writeText(shownVersion?.prompt_text ?? '')
              .then(() => setMessage('已复制 Prompt'))
              .catch(() => onError('复制失败'))
          }}
        >
          复制 Prompt
        </Button>
        <Button size="sm" variant="ghost" onClick={() => void run(() => assetApi.updateMeta(asset.id, { favorite: !asset.favorite }), '')}>
          {asset.favorite ? '★ 已收藏' : '☆ 收藏'}
        </Button>
        {asset.archived ? (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => void run(() => assetApi.restore(asset.id), '已从归档恢复')}>
            恢复
          </Button>
        ) : (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => void run(() => assetApi.archive(asset.id), '已归档（软删除）')}>
            归档
          </Button>
        )}
      </div>

      {message && <p className="ds-notice ds-notice--success" role="status">{message}</p>}

      <dl className="as-fields">
        <dt>类型</dt>
        <dd>{ASSET_TYPE_LABEL[asset.type]}</dd>
        <dt>Prompt</dt>
        <dd><pre>{shownVersion?.prompt_text || '（空）'}</pre></dd>
        <dt>Tags</dt>
        <dd>{(shownVersion?.tags ?? []).join('、') || '（无）'}</dd>
        <dt>备注</dt>
        <dd>{shownVersion?.notes || '（无）'}</dd>
      </dl>

      {asset.type === 'face' && (
        <section className="as-reference">
          <h4 className="as-reference__title">参考图（Face Reference · 来源：图库）</h4>
          {referenceImageId ? (
            <div className="as-reference__body">
              <img className="as-reference__thumb" src={imageContentUrl(referenceImageId)} alt="参考图" />
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => setRefPickerOpen(true)}>更换</Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => void clearReference()} title="移除参考图（创建新版本，旧版本保留原参考图）">
                移除
              </Button>
            </div>
          ) : (
            <div className="as-reference__body">
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => setRefPickerOpen(true)}>
                绑定参考图
              </Button>
              <span className="muted">从图库选择 1 张图片（新版才生效，旧版本保留）</span>
            </div>
          )}
        </section>
      )}

      {editOpen ? (
        <AssetEditor
          asset={asset}
          onCancel={() => setEditOpen(false)}
          onSaved={() => { setEditOpen(false); load() }}
        />
      ) : (
        <div className="as-footer">
          <Button variant="primary" onClick={() => setEditOpen(true)}>
            编辑（将创建新版本）
          </Button>
        </div>
      )}

      <section className="as-reference">
        <h4 className="as-reference__title">版本历史（不可变）</h4>
        <ul className="pp-versions__list">
          {versions.map((version) => (
            <li key={version.id} className="pp-versions__item">
              <div className="pp-versions__row">
                <span className="pp-versions__no">v{version.version_no}</span>
                <span className="muted">{formatDateTime(version.created_at)}</span>
                {asset.current_version?.id === version.id && <Badge>当前</Badge>}
                <span className="as-toolbar__spacer" />
                <Button size="xs" variant="ghost" onClick={() => setViewVersion(viewVersion === version.version_no ? null : version.version_no)}>
                  {viewVersion === version.version_no ? '看当前' : '查看'}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      {refPickerOpen && (
        <ImagePickerDrawer
          title="选择参考图"
          onClose={() => setRefPickerOpen(false)}
          onPicked={(image) => void bindReference(image.id)}
        />
      )}
    </Drawer>
  )
}
