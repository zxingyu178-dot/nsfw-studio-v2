import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiRequestError, assetApi } from '../../api/client'
import { ImagePickerDrawer } from '../../components/ImagePickerDrawer'
import {
  Badge,
  Button,
  Checkbox,
  Drawer,
  Field,
  Input,
  Modal,
  Select,
  Tabs,
  Textarea,
} from '../../components/ui'
import { formatDateTime } from '../../utils/format'
import {
  ASSET_TYPES,
  ASSET_TYPE_LABEL,
  assetPreviewUrl,
  imageContentUrl,
  type AssetDTO,
  type AssetType,
  type AssetVersionDTO,
} from '../../types/workbench'
import './assets.css'

/** 素材页（§四十一-§四十三、§五十四、§五十五）。 */
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
    <>
      <Tabs
        ariaLabel="素材分类"
        active={assetType}
        onChange={(key) => setAssetType(key as AssetType | 'all')}
        items={[
          { key: 'all', label: '全部' },
          ...ASSET_TYPES.map(({ key, label }) => ({ key, label })),
        ]}
      />

      <div className="as-toolbar">
        <Input
          placeholder="搜索素材名称 / Prompt"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <Checkbox
          label="显示已归档"
          checked={showArchived}
          onChange={(event) => setShowArchived(event.target.checked)}
        />
        <span className="as-toolbar__spacer" />
        <Button variant="primary" onClick={() => setUploadOpen(true)}>
          上传素材
        </Button>
      </div>

      {notice && (
        <p className={`ds-notice ds-notice--${notice.kind === 'ok' ? 'success' : 'error'}`} role="status">
          {notice.text}
        </p>
      )}
      {loading && <p className="muted">加载中…</p>}
      {error && <p className="ds-notice ds-notice--error">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <div className="as-empty">
          <h2 className="as-empty__title">还没有素材</h2>
          <p className="muted">点击“上传素材”创建第一个素材（支持 jpg / png / webp 预览图）。</p>
        </div>
      )}

      <div className="as-grid">
        {items.map((asset) => (
          <article key={asset.id} className="as-card" onClick={() => setDetailId(asset.id)}>
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
          onClose={() => { setDetailId(null); load() }}
          onUseInWorkbench={() => handleUseInWorkbench(detailId)}
          onError={(text) => setNotice({ kind: 'error', text })}
        />
      )}
    </>
  )
}

// ===== 上传对话框 =====
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
    <Modal
      open
      onClose={onClose}
      title="上传素材"
      size="md"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" disabled={busy || !name.trim()} onClick={() => void handleSubmit()}>
            创建
          </Button>
        </>
      }
    >
      <Field label="名称">
        <Input value={name} onChange={(event) => setName(event.target.value)} autoFocus />
      </Field>
      <Field label="类型">
        <Select
          value={assetType}
          onChange={(event) => setAssetType(event.target.value as AssetType)}
          options={ASSET_TYPES.map(({ key, label }) => ({ value: key, label }))}
        />
      </Field>
      <Field label="Prompt（该素材的关键词，用于生成时填入对应字段）">
        <Textarea rows={3} value={promptText} onChange={(event) => setPromptText(event.target.value)} />
      </Field>
      <Field label="Tags（逗号分隔）">
        <Input value={tags} onChange={(event) => setTags(event.target.value)} />
      </Field>
      <Field label="备注">
        <Input value={notes} onChange={(event) => setNotes(event.target.value)} />
      </Field>
      <Field label="预览图（jpg / jpeg / png / webp，≤10MB）">
        <Input
          type="file"
          accept=".jpg,.jpeg,.png,.webp"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </Field>
      {error && <p className="ds-notice ds-notice--error">{error}</p>}
    </Modal>
  )
}

// ===== 详情抽屉 =====
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
        <AssetEditForm
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
    <div className="as-edit">
      <h4 className="as-edit__title">编辑（保存后将创建新版本，旧版本保留）</h4>
      <Field label="Prompt">
        <Textarea rows={3} value={promptText} onChange={(event) => setPromptText(event.target.value)} />
      </Field>
      <Field label="Tags（逗号分隔）">
        <Input value={tags} onChange={(event) => setTags(event.target.value)} />
      </Field>
      <Field label="备注">
        <Input value={notes} onChange={(event) => setNotes(event.target.value)} />
      </Field>
      <Field label="替换预览图（可选）">
        <Input
          type="file"
          accept=".jpg,.jpeg,.png,.webp"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </Field>
      {error && <p className="ds-notice ds-notice--error">{error}</p>}
      <div className="as-actions">
        <Button variant="secondary" onClick={onCancel}>取消</Button>
        <Button variant="primary" disabled={busy} onClick={() => void handleSubmit()}>
          保存为新版本
        </Button>
      </div>
    </div>
  )
}
