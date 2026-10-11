import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiRequestError, assetApi, imageApi, jobApi, promptApi } from '../api/client'
import { formatDateTime } from '../utils/format'
import { Button, Field, Input, Select } from './ui'
import {
  ASSET_TYPES,
  MODULE_LABEL,
  imageContentUrl,
  shortJobId,
  type AssetType,
  type ImageDTO,
  type ImageProvenanceDTO,
  type JobDTO,
  type PromptDTO,
} from '../types/workbench'
import './LightboxInfoPanel.css'

/**
 * Phase 0.11 §四十六-§四十八：在【现有 Lightbox 右侧】扩展的信息栏（不推翻 Lightbox 本体）。
 *
 * 自包含：自行获取 Job / Provenance，并实现 复制 Prompt / 重新打开 Workbench /
 * 创建素材（记录 source_image_id）/ 设为 Prompt 封面（复用 preview_image_id）/ 删除（引用保护）。
 * 与 GalleryDetailDrawer 功能等价、组件独立，避免改动已稳定的抽屉逻辑（只扩展不破坏）。
 */
export interface LightboxInfoPanelProps {
  image: ImageDTO
  onUpdated: (image: ImageDTO) => void
  onDeleted: (imageId: string) => void
}

export function LightboxInfoPanel({ image, onUpdated, onDeleted }: LightboxInfoPanelProps) {
  const navigate = useNavigate()
  const [job, setJob] = useState<JobDTO | null>(null)
  const [provenance, setProvenance] = useState<ImageProvenanceDTO | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [assetType, setAssetType] = useState<AssetType>('face')
  const [assetName, setAssetName] = useState(`图库-${image.id.replace(/^img_/, '').slice(0, 8)}`)
  const [promptChoices, setPromptChoices] = useState<PromptDTO[]>([])
  const [coverPromptId, setCoverPromptId] = useState('')
  const [deleteArm, setDeleteArm] = useState(false)

  useEffect(() => {
    if (!image.job_id) return
    let cancelled = false
    jobApi.get(image.job_id)
      .then((detail) => { if (!cancelled) setJob(detail) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [image.job_id])

  useEffect(() => {
    let cancelled = false
    imageApi.provenance(image.id)
      .then((result) => { if (!cancelled) setProvenance(result) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [image.id])

  async function copyPrompt(): Promise<void> {
    const text = job?.positive_prompt_snapshot ?? ''
    try {
      await navigator.clipboard.writeText(text)
      setMessage('Prompt 已复制')
      setError(null)
    } catch {
      setError('复制失败（浏览器未授权剪贴板）')
    }
  }

  function openWorkbench(): void {
    imageApi.workbench(image.id)
      .then((result) => {
        navigate('/generate', { state: { workbench: { ...result.snapshot } } })
      })
      .catch((err: unknown) =>
        setError(err instanceof ApiRequestError ? err.message : '无法恢复到工作台'))
  }

  async function createAsset(): Promise<void> {
    if (busy || !assetName.trim()) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const response = await fetch(imageContentUrl(image.id))
      if (!response.ok) throw new Error('图片内容读取失败')
      const blob = await response.blob()
      const suffix = blob.type.includes('jpeg') ? '.jpg' : blob.type.includes('webp') ? '.webp' : '.png'
      const formData = new FormData()
      formData.set('name', assetName.trim())
      formData.set('type', assetType)
      formData.set('prompt_text', job?.positive_prompt_snapshot ?? '')
      formData.set('source_image_id', image.id)
      formData.set('preview', new File([blob], `image_${image.id}${suffix}`, { type: blob.type || 'image/png' }))
      await assetApi.create(formData)
      setMessage('素材已创建（已记录 source_image_id）')
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '创建素材失败')
    } finally {
      setBusy(false)
    }
  }

  function openPromptChooser(): void {
    promptApi.list({ limit: 200 })
      .then((page) => setPromptChoices(page.items))
      .catch((err: unknown) => setError(err instanceof ApiRequestError ? err.message : '无法加载 Prompt 列表'))
  }

  async function applyCover(): Promise<void> {
    if (!coverPromptId) {
      setError('请先选择一个 Prompt')
      return
    }
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await promptApi.setPreviewImage(coverPromptId, image.id)
      setMessage('已设为该 Prompt 封面')
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '设置封面失败')
    } finally {
      setBusy(false)
    }
  }

  async function deleteImage(): Promise<void> {
    if (!deleteArm) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const preview = await imageApi.cleanupRejected({ image_ids: [image.id], confirm: false })
      if ((preview.protected_count ?? 0) > 0) {
        setError('该图片被 Prompt / 素材 / 配方引用，禁止删除（已保护）。')
        setDeleteArm(false)
        return
      }
      const result = await imageApi.cleanupRejected({ image_ids: [image.id], confirm: true })
      onUpdated({ ...image })
      onDeleted(image.id)
      void result
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '删除失败')
    } finally {
      setBusy(false)
    }
  }

  const moduleLabel = provenance?.module_id
    ? (MODULE_LABEL[provenance.module_id ?? ''] ?? provenance.module_id)
    : '—'

  return (
    <aside className="lb-side" aria-label="图片信息">
      <dl className="lb-side__fields">
        <dt>尺寸</dt>
        <dd>{image.width} × {image.height}</dd>
        <dt>生成时间</dt>
        <dd>{formatDateTime(image.created_at)}</dd>
        <dt>Seed</dt>
        <dd>{image.seed ?? '—'}</dd>
        <dt>来源 Job</dt>
        <dd>{image.job_id ? shortJobId(image.job_id) : '—（导入图片）'}</dd>
        <dt>模块</dt>
        <dd>{moduleLabel}</dd>
        <dt>Recipe</dt>
        <dd className="muted">—（图片未直接关联配方快照）</dd>
        <dt>Prompt</dt>
        <dd><pre>{job?.positive_prompt_snapshot ?? '（不可用）'}</pre></dd>
        <dt>Negative</dt>
        <dd><pre>{job?.negative_prompt_snapshot ?? '（无）'}</pre></dd>
      </dl>

      <div className="lb-side__actions">
        <Button size="sm" variant="ghost" onClick={() => void copyPrompt()}>复制 Prompt</Button>
        <Button size="sm" variant="secondary" disabled={!image.job_id} onClick={openWorkbench}>
          重新打开 Workbench
        </Button>
      </div>

      <section className="lb-side__block">
        <h5>创建素材</h5>
        <Field label="类型">
          <Select
            value={assetType}
            onChange={(event) => setAssetType(event.target.value as AssetType)}
            options={ASSET_TYPES.map(({ key, label }) => ({ value: key, label }))}
          />
        </Field>
        <Field label="名称">
          <Input value={assetName} onChange={(event) => setAssetName(event.target.value)} />
        </Field>
        <Button size="sm" variant="primary" disabled={busy || !assetName.trim()} onClick={() => void createAsset()}>
          创建素材
        </Button>
      </section>

      <section className="lb-side__block">
        <h5>设为 Prompt 封面</h5>
        {promptChoices.length === 0 ? (
          <Button size="sm" variant="secondary" onClick={openPromptChooser}>选择 Prompt</Button>
        ) : (
          <>
            <Field label="Prompt">
              <Select
                value={coverPromptId}
                onChange={(event) => setCoverPromptId(event.target.value)}
                options={[{ value: '', label: '（请选择）' }, ...promptChoices.map((p) => ({ value: p.id, label: p.name }))]}
              />
            </Field>
            <Button size="sm" variant="primary" disabled={busy || !coverPromptId} onClick={() => void applyCover()}>
              设为封面
            </Button>
          </>
        )}
      </section>

      <section className="lb-side__block">
        <h5>删除图片</h5>
        {!deleteArm ? (
          <Button size="sm" variant="danger" onClick={() => setDeleteArm(true)}>删除此图片</Button>
        ) : (
          <div className="lb-side__actions">
            <Button size="sm" variant="danger" disabled={busy} onClick={() => void deleteImage()}>
              {busy ? '处理中…' : '确认删除（不可恢复）'}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setDeleteArm(false)}>取消</Button>
          </div>
        )}
      </section>

      {message && <p className="ds-notice ds-notice--success" role="status">{message}</p>}
      {error && <p className="ds-notice ds-notice--error">{error}</p>}
    </aside>
  )
}

export default LightboxInfoPanel
