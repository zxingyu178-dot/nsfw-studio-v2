import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiRequestError, assetApi } from '../../api/client'
import { formatDateTime } from '../../utils/format'
import {
  ASSET_TYPES,
  ASSET_TYPE_LABEL,
  assetPreviewUrl,
  type AssetDTO,
  type AssetType,
  type AssetVersionDTO,
} from '../../types/workbench'

/** 素材页（规范 §四十一-§四十三、§五十四、§五十五）。 */
export default function AssetsPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState<AssetDTO[]>([])
  const [assetType, setAssetType] = useState<AssetType | 'all'>('all')
  const [search, setSearch] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    assetApi
      .list({
        type: assetType === 'all' ? null : assetType,
        search: search.trim() || undefined,
        archived: showArchived ? null : false,
        limit: 100,
      })
      .then((page) => setItems(page.items))
      .catch((err: unknown) => setError(err instanceof ApiRequestError ? err.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [assetType, search, showArchived])

  useEffect(() => {
    const timer = window.setTimeout(load, 250)
    return () => window.clearTimeout(timer)
  }, [load])

  function handleUseInWorkbench(assetId: string): void {
    assetApi
      .workbench(assetId)
      .then((result) => {
        setDetailId(null)
        navigate('/generate', { state: { workbench: result.snapshot } })
      })
      .catch((err: unknown) => {
        setNotice({ kind: 'error', text: err instanceof ApiRequestError ? err.message : '操作失败' })
      })
  }

  return (
    <section className="page page--wide">
      <div className="tabs" role="tablist" aria-label="素材分类">
        <button
          type="button"
          role="tab"
          aria-selected={assetType === 'all'}
          className={`tabs__item${assetType === 'all' ? ' tabs__item--active' : ''}`}
          onClick={() => setAssetType('all')}
        >
          全部
        </button>
        {ASSET_TYPES.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={assetType === key}
            className={`tabs__item${assetType === key ? ' tabs__item--active' : ''}`}
            onClick={() => setAssetType(key)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="toolbar">
        <input
          className="input toolbar__search"
          placeholder="搜索素材名称 / Prompt"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <label className="check check--inline">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(event) => setShowArchived(event.target.checked)}
          />
          <span>显示已归档</span>
        </label>
        <span className="toolbar__spacer" />
        <button type="button" className="btn btn--primary" onClick={() => setUploadOpen(true)}>
          上传素材
        </button>
      </div>

      {notice && <p className={`notice notice--${notice.kind}`} role="status">{notice.text}</p>}
      {loading && <p className="muted">加载中…</p>}
      {error && <p className="notice notice--error">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <div className="empty-state">
          <h1 className="empty-state__title">还没有素材</h1>
          <p className="empty-state__desc">点击"上传素材"创建第一个素材（支持 jpg / png / webp 预览图）。</p>
        </div>
      )}

      <div className="asset-grid">
        {items.map((asset) => (
          <article key={asset.id} className="asset-card" onClick={() => setDetailId(asset.id)}>
            <div className="asset-card__thumb">
              {asset.current_version?.preview_path ? (
                <img src={assetPreviewUrl(asset.id)} alt={asset.name} loading="lazy" />
              ) : (
                <span className="asset-thumb-placeholder">{ASSET_TYPE_LABEL[asset.type]}</span>
              )}
            </div>
            <div className="asset-card__body">
              <h3 className="asset-card__title">
                {asset.favorite && <span title="已收藏">★ </span>}
                {asset.name}
                {asset.archived && <span className="badge">已归档</span>}
              </h3>
              <p className="asset-card__tags">
                {(asset.current_version?.tags ?? []).slice(0, 3).map((tag) => (
                  <span key={tag} className="badge">{tag}</span>
                ))}
              </p>
            </div>
          </article>
        ))}
      </div>

      {uploadOpen && (
        <UploadDialog
          defaultType={assetType === 'all' ? 'clothing' : assetType}
          onClose={() => setUploadOpen(false)}
          onCreated={(message_) => {
            setUploadOpen(false)
            setNotice({ kind: 'ok', text: message_ })
            load()
          }}
        />
      )}

      {detailId && (
        <AssetDetailDrawer
          assetId={detailId}
          onClose={() => {
            setDetailId(null)
            load()
          }}
          onUseInWorkbench={() => handleUseInWorkbench(detailId)}
          onError={(text) => setNotice({ kind: 'error', text })}
        />
      )}
    </section>
  )
}

// ===== 上传对话框（新建素材 + v1） =====
interface UploadDialogProps {
  defaultType: AssetType
  onClose: () => void
  onCreated: (message: string) => void
}

function UploadDialog({ defaultType, onClose, onCreated }: UploadDialogProps) {
  const [name, setName] = useState('')
  const [assetType, setAssetType] = useState<AssetType>(defaultType)
  const [promptText, setPromptText] = useState('')
  const [notes, setNotes] = useState('')
  const [tags, setTags] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(): Promise<void> {
    if (busy || !name.trim()) return
    setBusy(true)
    setError(null)
    const formData = new FormData()
    formData.set('name', name.trim())
    formData.set('type', assetType)
    formData.set('prompt_text', promptText)
    formData.set('notes', notes)
    formData.set(
      'tags',
      JSON.stringify(tags.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean)),
    )
    formData.set('favorite', 'false')
    if (file) formData.set('preview', file)
    try {
      await assetApi.create(formData)
      onCreated('素材已创建')
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '创建失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="上传素材"
        onClick={(event) => event.stopPropagation()}
      >
        <h3 className="modal__title">上传素材</h3>
        <div className="field">
          <label className="field__label" htmlFor="upload-name">名称</label>
          <input id="upload-name" className="input" value={name} onChange={(event) => setName(event.target.value)} autoFocus />
        </div>
        <div className="field">
          <label className="field__label" htmlFor="upload-type">类型</label>
          <select
            id="upload-type"
            className="input"
            value={assetType}
            onChange={(event) => setAssetType(event.target.value as AssetType)}
          >
            {ASSET_TYPES.map(({ key, label }) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="field__label" htmlFor="upload-prompt">Prompt（该素材的关键词，用于生成时填入对应字段）</label>
          <textarea
            id="upload-prompt"
            className="input input--area"
            rows={3}
            value={promptText}
            onChange={(event) => setPromptText(event.target.value)}
          />
        </div>
        <div className="field">
          <label className="field__label" htmlFor="upload-tags">Tags（逗号分隔）</label>
          <input id="upload-tags" className="input" value={tags} onChange={(event) => setTags(event.target.value)} />
        </div>
        <div className="field">
          <label className="field__label" htmlFor="upload-notes">备注</label>
          <input id="upload-notes" className="input" value={notes} onChange={(event) => setNotes(event.target.value)} />
        </div>
        <div className="field">
          <label className="field__label" htmlFor="upload-file">预览图（jpg / jpeg / png / webp，≤10MB）</label>
          <input
            id="upload-file"
            className="input"
            type="file"
            accept=".jpg,.jpeg,.png,.webp"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </div>
        {error && <p className="notice notice--error">{error}</p>}
        <div className="modal__actions">
          <button type="button" className="btn" onClick={onClose}>取消</button>
          <button type="button" className="btn btn--primary" disabled={busy || !name.trim()} onClick={() => void handleSubmit()}>
            创建
          </button>
        </div>
      </div>
    </div>
  )
}

// ===== 详情抽屉（大预览 / 编辑产生新版本 / 版本历史） =====
interface DetailDrawerProps {
  assetId: string
  onClose: () => void
  onUseInWorkbench: () => void
  onError: (message: string) => void
}

function AssetDetailDrawer({ assetId, onClose, onUseInWorkbench, onError }: DetailDrawerProps) {
  const [asset, setAsset] = useState<AssetDTO | null>(null)
  const [versions, setVersions] = useState<AssetVersionDTO[]>([])
  const [viewVersion, setViewVersion] = useState<number | null>(null)
  const [editOpen, setEditOpen] = useState(false)
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

  if (!asset) return <div className="drawer-backdrop"><aside className="drawer"><p className="muted">加载中…</p></aside></div>

  const shownVersion =
    viewVersion === null
      ? asset.current_version
      : (versions.find((version) => version.version_no === viewVersion) ?? asset.current_version)

  async function run(action: () => Promise<unknown>, okText: string): Promise<void> {
    setBusy(true)
    setMessage(null)
    try {
      await action()
      load()
      setMessage(okText)
    } catch (err) {
      onError(err instanceof ApiRequestError ? err.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="drawer drawer--wide"
        role="dialog"
        aria-modal="true"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drawer__header">
          <h3 className="drawer__title">{asset.name}</h3>
          <button type="button" className="btn btn--ghost btn--sm" onClick={onClose} aria-label="关闭">✕</button>
        </header>

        <div className="asset-detail__preview">
          {shownVersion?.preview_path ? (
            <img src={assetPreviewUrl(asset.id, viewVersion ?? undefined)} alt={asset.name} />
          ) : (
            <span className="asset-thumb-placeholder asset-thumb-placeholder--lg">
              {ASSET_TYPE_LABEL[asset.type]}
            </span>
          )}
        </div>

        <div className="drawer__meta-actions">
          <button type="button" className="btn btn--primary btn--sm" onClick={onUseInWorkbench}>
            用于生成
          </button>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            disabled={!shownVersion?.prompt_text}
            onClick={() => {
              void navigator.clipboard
                .writeText(shownVersion?.prompt_text ?? '')
                .then(() => setMessage('已复制 Prompt'))
                .catch(() => onError('复制失败'))
            }}
          >
            复制 Prompt
          </button>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => void run(() => assetApi.updateMeta(asset.id, { favorite: !asset.favorite }), '')}
          >
            {asset.favorite ? '★ 已收藏' : '☆ 收藏'}
          </button>
          {asset.archived ? (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              disabled={busy}
              onClick={() => void run(() => assetApi.restore(asset.id), '已从归档恢复')}
            >
              恢复
            </button>
          ) : (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              disabled={busy}
              onClick={() => void run(() => assetApi.archive(asset.id), '已归档（软删除）')}
            >
              归档
            </button>
          )}
        </div>

        {message && <p className="notice notice--ok" role="status">{message}</p>}

        <dl className="asset-detail__fields">
          <dt>类型</dt>
          <dd>{ASSET_TYPE_LABEL[asset.type]}</dd>
          <dt>Prompt</dt>
          <dd><pre className="asset-detail__prompt">{shownVersion?.prompt_text || '（空）'}</pre></dd>
          <dt>Tags</dt>
          <dd>{(shownVersion?.tags ?? []).join('、') || '（无）'}</dd>
          <dt>备注</dt>
          <dd>{shownVersion?.notes || '（无）'}</dd>
        </dl>

        {editOpen && (
          <AssetEditForm
            asset={asset}
            onCancel={() => setEditOpen(false)}
            onSaved={() => {
              setEditOpen(false)
              load()
            }}
          />
        )}
        {!editOpen && (
          <div className="pane__footer">
            <button type="button" className="btn btn--primary" onClick={() => setEditOpen(true)}>
              编辑（将创建新版本）
            </button>
          </div>
        )}

        <section className="version-history">
          <h4 className="version-history__title">版本历史（不可变）</h4>
          <ul className="version-history__list">
            {versions.map((version) => (
              <li key={version.id} className="version-history__item">
                <div className="version-history__row">
                  <span className="version-history__no">v{version.version_no}</span>
                  <span className="muted">{formatDateTime(version.created_at)}</span>
                  {asset.current_version?.id === version.id && <span className="badge">当前</span>}
                  <span className="toolbar__spacer" />
                  <button
                    type="button"
                    className="btn btn--ghost btn--xs"
                    onClick={() => setViewVersion(viewVersion === version.version_no ? null : version.version_no)}
                  >
                    {viewVersion === version.version_no ? '看当前' : '查看'}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </aside>
    </div>
  )
}

interface EditFormProps {
  asset: AssetDTO
  onCancel: () => void
  onSaved: () => void
}

function AssetEditForm({ asset, onCancel, onSaved }: EditFormProps) {
  const current = asset.current_version
  const [promptText, setPromptText] = useState(current?.prompt_text ?? '')
  const [notes, setNotes] = useState(current?.notes ?? '')
  const [tags, setTags] = useState((current?.tags ?? []).join('，'))
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(): Promise<void> {
    if (busy) return
    setBusy(true)
    setError(null)
    const formData = new FormData()
    formData.set('prompt_text', promptText)
    formData.set('notes', notes)
    formData.set(
      'tags',
      JSON.stringify(tags.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean)),
    )
    if (file) formData.set('preview', file)
    try {
      await assetApi.addVersion(asset.id, formData)
      onSaved()
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="asset-edit">
      <h4 className="version-history__title">编辑（保存后将创建新版本，旧版本保留）</h4>
      <div className="field">
        <label className="field__label" htmlFor="edit-prompt">Prompt</label>
        <textarea
          id="edit-prompt"
          className="input input--area"
          rows={3}
          value={promptText}
          onChange={(event) => setPromptText(event.target.value)}
        />
      </div>
      <div className="field">
        <label className="field__label" htmlFor="edit-tags">Tags（逗号分隔）</label>
        <input id="edit-tags" className="input" value={tags} onChange={(event) => setTags(event.target.value)} />
      </div>
      <div className="field">
        <label className="field__label" htmlFor="edit-notes">备注</label>
        <input id="edit-notes" className="input" value={notes} onChange={(event) => setNotes(event.target.value)} />
      </div>
      <div className="field">
        <label className="field__label" htmlFor="edit-file">替换预览图（可选）</label>
        <input
          id="edit-file"
          className="input"
          type="file"
          accept=".jpg,.jpeg,.png,.webp"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </div>
      {error && <p className="notice notice--error">{error}</p>}
      <div className="modal__actions">
        <button type="button" className="btn" onClick={onCancel}>取消</button>
        <button type="button" className="btn btn--primary" disabled={busy} onClick={() => void handleSubmit()}>
          保存为新版本
        </button>
      </div>
    </div>
  )
}
