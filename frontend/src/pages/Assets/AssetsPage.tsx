import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiRequestError, assetApi } from '../../api/client'
import {
  Button,
  Checkbox,
  Field,
  Input,
  Modal,
  Select,
  Tabs,
  Textarea,
} from '../../components/ui'
import {
  ASSET_TYPES,
  type AssetDTO,
  type AssetType,
} from '../../types/workbench'
import { AssetGrid } from './AssetGrid'
import { AssetDetailDrawer } from './AssetDetailDrawer'
import { useInfiniteList } from '../Prompt/useInfiniteList'
import './assets.css'

/** 素材页（§四十一-§四十三、§五十四、§五十五）。 */
export default function AssetsPage() {
  const navigate = useNavigate()
  const [assetType, setAssetType] = useState<AssetType | 'all'>('all')
  const [search, setSearch] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)

  // Phase 0.12：移除前端 limit=100 的隐形上限，改为 offset 分页 + 搜索 stale guard。
  const fetcher = useCallback(
    (limit: number, offset: number) =>
      assetApi.list({
        type: assetType === 'all' ? null : assetType,
        search: search.trim() || undefined,
        archived: showArchived ? null : false,
        limit,
        offset,
      }),
    [assetType, search, showArchived],
  )

  const {
    items,
    total,
    hasMore,
    initialLoading: loading,
    loadingMore,
    error,
    reload: load,
    loadMore,
  } = useInfiniteList<AssetDTO>({ pageSize: 60, fetcher, reloadDeps: [fetcher] })

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

      <AssetGrid items={items} onOpen={setDetailId} />

      {!loading && !error && items.length > 0 && (
        <div className="as-loadmore">
          {hasMore ? (
            <Button variant="secondary" loading={loadingMore} disabled={loadingMore} onClick={loadMore}>
              {loadingMore ? '加载中…' : '加载更多'}
            </Button>
          ) : (
            <span className="muted">已加载全部 {total} 条</span>
          )}
          <span className="muted">已加载 {items.length} / 共 {total}</span>
        </div>
      )}

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
