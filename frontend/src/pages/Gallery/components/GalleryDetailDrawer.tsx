import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiRequestError, assetApi, imageApi, jobApi, promptApi } from '../../../api/client'
import { formatDateTime } from '../../../utils/format'
import {
  Button,
  Drawer,
  Field,
  Input,
  Select,
} from '../../../components/ui'
import {
  ASSET_TYPES,
  IMAGE_KIND_LABEL,
  IMAGE_SOURCE_LABEL,
  IMAGE_STATUS_LABEL,
  MODULE_LABEL,
  imageContentUrl,
  normalizeImageStatus,
  shortJobId,
  type AssetType,
  type ImageDTO,
  type ImageProvenanceDTO,
  type ImageReviewStatus,
  type ImageVersionsDTO,
  type JobDTO,
  type PromptDTO,
  type WorkbenchSnapshot,
} from '../../../types/workbench'
import { emptyWorkbenchSnapshot } from '../../../stores/workbenchStore'

/**
 * Phase 0.12 Task9：图片详情抽屉（从 GalleryPage 抽取，行为不变）。
 * §四十六-§四十八：信息栏 + 版本链接 + 审核/复用/创建素材/设封面 + v0.11 二分删除语义。
 */

export interface GalleryDetailDrawerProps {
  image: ImageDTO
  onClose: () => void
  onUpdated: (image: ImageDTO) => void
  onSelectImage: (image: ImageDTO) => void
  onUpscale: (imageId: string) => void
  upscaling: boolean
  onUseAsInput: (image: ImageDTO) => void
  onReviewStart: (previous: ImageReviewStatus) => void
  onFavoriteStart: (previous: boolean) => void
  onPreviewLightbox: () => void
  onDeleted: () => void
}

export function GalleryDetailDrawer({
  image, onClose, onUpdated, onSelectImage, onUpscale, upscaling,
  onUseAsInput, onReviewStart, onFavoriteStart, onPreviewLightbox, onDeleted,
}: GalleryDetailDrawerProps) {
  const navigate = useNavigate()
  const [job, setJob] = useState<JobDTO | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [versions, setVersions] = useState<ImageVersionsDTO | null>(null)
  const [provenance, setProvenance] = useState<ImageProvenanceDTO | null>(null)
  const [assetType, setAssetType] = useState<AssetType>('face')
  const [assetName, setAssetName] = useState(`图库-${image.id.replace(/^img_/, '').slice(0, 8)}`)
  // Phase 0.11：设为 Prompt 封面
  const [promptChoices, setPromptChoices] = useState<PromptDTO[]>([])
  const [coverPromptId, setCoverPromptId] = useState('')
  // Phase 0.11：删除确认
  const [deleteArm, setDeleteArm] = useState(false)

  useEffect(() => {
    if (!image.job_id) return
    let cancelled = false
    jobApi
      .get(image.job_id)
      .then((detail) => { if (!cancelled) setJob(detail) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [image.job_id])

  useEffect(() => {
    let cancelled = false
    setVersions(null)
    imageApi
      .versions(image.id)
      .then((result) => { if (!cancelled) setVersions(result) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [image.id])

  useEffect(() => {
    let cancelled = false
    setProvenance(null)
    imageApi
      .provenance(image.id)
      .then((result) => { if (!cancelled) setProvenance(result) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [image.id])

  function run(action: () => Promise<ImageDTO>, okText: string): Promise<void> {
    setBusy(true)
    setError(null)
    setMessage(null)
    return action()
      .then((updated) => {
        onUpdated(updated)
        setMessage(okText)
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiRequestError ? err.message : '操作失败')
      })
      .finally(() => setBusy(false))
  }

  function openInWorkbench(useSeed: boolean): void {
    setError(null)
    imageApi
      .workbench(image.id)
      .then((result) => {
        const snapshot = { ...result.snapshot }
        if (useSeed && result.seed !== null) {
          snapshot.seed = result.seed
          snapshot.seed_mode = 'fixed'
          snapshot.count = 1
        }
        onClose()
        navigate('/generate', { state: { workbench: snapshot } })
      })
      .catch((err: unknown) =>
        setError(err instanceof ApiRequestError ? err.message : '无法恢复到工作台'),
      )
  }

  function startImg2Img(): void {
    setError(null)
    const go = (base: WorkbenchSnapshot): void => {
      const snapshot: WorkbenchSnapshot = {
        ...base,
        generation_mode: 'image',
        input_images: [{ role: 'source', image_id: image.id }],
      }
      onClose()
      navigate('/generate', { state: { workbench: snapshot } })
    }
    if (!image.job_id) {
      go(emptyWorkbenchSnapshot())
      return
    }
    imageApi
      .workbench(image.id)
      .then((result) => go(result.snapshot))
      .catch((err: unknown) =>
        setError(err instanceof ApiRequestError ? err.message : '无法恢复原图生成配置'),
      )
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
      formData.set(
        'preview',
        new File([blob], `image_${image.id}${suffix}`, { type: blob.type || 'image/png' }),
      )
      await assetApi.create(formData)
      setMessage('素材已创建（独立资产文件，已记录 source_image_id）')
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '创建素材失败')
    } finally {
      setBusy(false)
    }
  }

  function openPromptChooser(): void {
    setError(null)
    setMessage(null)
    promptApi
      .list({ limit: 200 })
      .then((page) => setPromptChoices(page.items))
      .catch((err: unknown) => setError(err instanceof ApiRequestError ? err.message : '无法加载 Prompt 列表'))
  }

  async function applyPromptCover(): Promise<void> {
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

  async function copyPrompt(): Promise<void> {
    const text = job?.positive_prompt_snapshot ?? ''
    try {
      await navigator.clipboard.writeText(text)
      setMessage('Prompt 已复制')
    } catch {
      setError('复制失败')
    }
  }

  /** Phase 0.11.1：普通图（非 REJECT）“淘汰此图”——仅置 REJECT、保留文件，不物理删除。 */
  async function softReject(): Promise<void> {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      onReviewStart(displayStatus)
      onUpdated(await imageApi.setStatus(image.id, { status: 'REJECT' }))
      setMessage('已移入废片（REJECT），文件仍保留；可在「清理废片」中永久删除。')
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  /** Phase 0.11.1：仅 REJECT 图“永久删除此废片”——先引用保护预览，确认后真删；
   *  只有 deleted_count===1 才真正从 UI 移除，杜绝假成功。 */
  async function deleteImage(): Promise<void> {
    if (!deleteArm) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const preview = await imageApi.cleanupRejected({ image_ids: [image.id], confirm: false })
      if ((preview.protected_count ?? 0) > 0) {
        const reason = preview.protected_items?.[0]?.reasons?.join('；')
        setError(`该图片被引用，禁止删除（已保护）${reason ? `：${reason}` : ''}。`)
        setDeleteArm(false)
        return
      }
      const result = await imageApi.cleanupRejected({ image_ids: [image.id], confirm: true })
      if ((result.deleted_count ?? 0) === 1) {
        onDeleted()
      } else {
        setError(`后端实际删除 ${result.deleted_count ?? 0} 张（预期 1），未从列表移除。`)
        setDeleteArm(false)
      }
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '删除失败')
    } finally {
      setBusy(false)
    }
  }

  const displayStatus = normalizeImageStatus(image)
  const sourceModule = provenance?.module_id ?? job?.module_id ?? null

  return (
    <Drawer
      open
      onClose={onClose}
      width="wide"
      title={
        <>
          图片详情
          {image.favorite && <span title="收藏"> ★</span>}
        </>
      }
    >
      <div className="gal-detail">
        <div className="gal-detail__preview" onDoubleClick={onPreviewLightbox} title="双击放大查看">
          <img src={imageContentUrl(image.id)} alt="" />
          {image.kind === 'upscaled' && <span className="gal-detail__hd">HD</span>}
        </div>

        <section className="gal-detail-section" aria-labelledby="gal-overview-title">
          <h3 id="gal-overview-title" className="gal-section-title">概览</h3>
          <div className="gal-detail-chips" aria-label="图片状态">
            <span className="gal-detail-chip">{IMAGE_STATUS_LABEL[displayStatus]}</span>
            {image.favorite && <span className="gal-detail-chip gal-detail-chip--accent">★ 收藏</span>}
          </div>
          <dl className="gal-fields">
            <dt>尺寸</dt>
            <dd className="gal-field-value--mono">{image.width} × {image.height}</dd>
            <dt>Seed</dt>
            <dd className="gal-field-value--mono">{image.seed ?? '—'}</dd>
            <dt>生成时间</dt>
            <dd className="gal-field-value--mono">{formatDateTime(image.created_at)}</dd>
            <dt>来源</dt>
            <dd className="gal-field-value--mono gal-detail-source">
              <span>{sourceModule ? MODULE_LABEL[sourceModule] ?? sourceModule : IMAGE_SOURCE_LABEL[image.source] ?? image.source}</span>
              <span aria-hidden="true">/</span>
              <span>{image.job_id ? shortJobId(image.job_id) : '外部导入'}</span>
            </dd>
            <dt>类型</dt>
            <dd>{IMAGE_KIND_LABEL[image.kind] ?? image.kind}</dd>
            <dt>Prompt</dt>
            <dd><pre>{job?.positive_prompt_snapshot || '（不可用）'}</pre></dd>
            <dt>Negative</dt>
            <dd><pre>{job?.negative_prompt_snapshot || '（无）'}</pre></dd>
          </dl>
        </section>

        <section className="gal-detail-section" aria-labelledby="gal-actions-title">
          <h3 id="gal-actions-title" className="gal-section-title">操作</h3>
          <div className="gal-actions gal-actions--primary">
            <Button size="sm" variant="primary" disabled={!image.job_id} onClick={() => openInWorkbench(false)}>
              在生成工作台中打开
            </Button>
            <Button size="sm" variant="secondary" disabled={!image.job_id} onClick={() => openInWorkbench(true)}>
              使用原图 Seed
            </Button>
            <a
              className="ds-btn ds-btn--secondary ds-btn--sm gal-detail__download"
              href={imageContentUrl(image.id)}
              download
              title="下载原图"
              aria-label="下载原图"
            >
              下载原图
            </a>
          </div>
          <div className="gal-actions">
            <Button size="sm" variant="secondary" onClick={() => onUseAsInput(image)}>
              用作输入图片
            </Button>
            <Button size="sm" variant="secondary" onClick={startImg2Img}>
              以此图进行图生图
            </Button>
            <Button size="sm" variant="ghost" onClick={() => void copyPrompt()}>
              复制 Prompt
            </Button>
            <Button
              size="sm" variant={displayStatus === 'KEEP' || displayStatus === 'ARCHIVED' ? 'primary' : 'secondary'}
              disabled={busy}
              onClick={() => { onReviewStart(displayStatus); void run(() => imageApi.setStatus(image.id, { status: 'KEEP' }), '已保留') }}
            >
              保留 (K)
            </Button>
            {displayStatus !== 'NEW' && (
              <Button
                size="sm" variant="ghost" disabled={busy}
                onClick={() => { onReviewStart(displayStatus); void run(() => imageApi.setStatus(image.id, { status: 'NEW' }), '已恢复为待审核') }}
              >
                取消审核
              </Button>
            )}
            <Button
              size="sm" variant="ghost" disabled={busy}
              onClick={() => { onFavoriteStart(image.favorite); void run(() => imageApi.favorite(image.id, !image.favorite), image.favorite ? '已取消收藏' : '已收藏') }}
            >
              {image.favorite ? '★ 已收藏' : '☆ 收藏 (F)'}
            </Button>
          </div>
        </section>

        <section className="gal-detail-section" aria-labelledby="gal-versions-title">
          <h3 id="gal-versions-title" className="gal-section-title">版本</h3>
          <div className="gal-version-links">
            <Button size="sm" variant="secondary" disabled={upscaling} onClick={() => onUpscale(image.id)}>
              {upscaling ? '提交中…' : '高清放大'}
            </Button>
            {versions?.parent && (
              <Button size="sm" variant="ghost" onClick={() => onSelectImage(versions.parent as ImageDTO)}>
                来源原图：{IMAGE_KIND_LABEL[versions.parent.kind] ?? versions.parent.kind} · 查看
              </Button>
            )}
            {(versions?.children.length ?? 0) > 0 ? (
              <div className="gal-version-children">
                <span className="muted">派生版本：</span>
                {versions!.children.map((child) => {
                  const scale = image.width > 0 ? Math.round(child.width / image.width) : 0
                  return (
                    <Button
                      key={child.id}
                      size="sm" variant="ghost"
                      onClick={() => onSelectImage(child)}
                    >
                      {IMAGE_KIND_LABEL[child.kind] ?? child.kind}
                      <span className="gal-field-value--mono">
                        {scale > 1 ? ` ×${scale}` : ''} · {child.width}×{child.height}
                      </span>
                    </Button>
                  )
                })}
              </div>
            ) : (
              !versions?.parent && <p className="muted gal-version-empty">暂无派生版本</p>
            )}
          </div>
        </section>

        <section className="gal-detail-section" aria-labelledby="gal-advanced-title">
          <h3 id="gal-advanced-title" className="gal-section-title">高级信息</h3>
          <details className="gal-detail-advanced">
            <summary className="muted">高级信息（来源原图 / Stage / Workflow 版本）</summary>
            <dl className="gal-fields">
              <dt>来源任务</dt>
              <dd className="gal-field-value--mono">{provenance?.job_id ? shortJobId(provenance.job_id) : image.job_id ? shortJobId(image.job_id) : '外部导入'}</dd>
              <dt>Seed</dt>
              <dd className="gal-field-value--mono">{provenance?.seed ?? '—'}</dd>
              <dt>管线</dt>
              <dd>
                {!image.job_id
                  ? '外部导入'
                  : provenance?.kind === 'upscaled'
                    ? `基础生成 → 高清${provenance.scale && provenance.scale > 1 ? ` ×${provenance.scale}` : ''}`
                    : sourceModule ? MODULE_LABEL[sourceModule] ?? sourceModule : '—'}
              </dd>
              <dt>来源原图</dt>
              <dd className="gal-field-value--mono">{provenance?.parent_image_id ?? image.parent_image_id ?? '（本身为原图）'}</dd>
              <dt>Stage</dt>
              <dd className="gal-field-value--mono">{provenance?.stage_index ?? '—'}</dd>
              <dt>模块</dt>
              <dd className="gal-field-value--mono">{sourceModule ?? '—'}{provenance?.module_version ? ` ${provenance.module_version}` : ''}</dd>
              <dt>引擎 / Binding</dt>
              <dd className="gal-field-value--mono">{provenance?.provider ?? job?.provider ?? '—'}{provenance?.binding_version ? ` ${provenance.binding_version}` : ''}</dd>
              <dt>workflow_hash</dt>
              <dd className="gal-field-value--mono">{provenance?.workflow_hash ?? job?.workflow_hash ?? '—'}</dd>
              <dt>binding_hash</dt>
              <dd className="gal-field-value--mono">{provenance?.binding_hash ?? job?.binding_hash ?? '—'}</dd>
            </dl>
          </details>
        </section>

        {message && <p className="ds-notice ds-notice--success" role="status">{message}</p>}
        {error && <p className="ds-notice ds-notice--error">{error}</p>}

        {/* 从图库创建素材（§四十八） */}
        <section className="gal-detail-section gal-asset-edit">
          <h3 className="gal-section-title">创建素材（独立资产文件，图片以后被清理不影响素材）</h3>
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
          <Button
            size="sm" variant="primary"
            disabled={busy || !assetName.trim()}
            onClick={() => void createAsset()}
          >
            创建素材
          </Button>
        </section>

        {/* Phase 0.11：设为 Prompt 封面 */}
        <section className="gal-detail-section gal-asset-edit">
          <h3 className="gal-section-title">设为 Prompt 封面</h3>
          {promptChoices.length === 0 ? (
            <Button size="sm" variant="secondary" disabled={busy} onClick={openPromptChooser}>
              选择 Prompt
            </Button>
          ) : (
            <>
              <Field label="Prompt">
                <Select
                  value={coverPromptId}
                  onChange={(event) => setCoverPromptId(event.target.value)}
                  options={[{ value: '', label: '（请选择）' }, ...promptChoices.map((p) => ({ value: p.id, label: p.name }))]}
                />
              </Field>
              <Button size="sm" variant="primary" disabled={busy || !coverPromptId} onClick={() => void applyPromptCover()}>
                设为封面
              </Button>
            </>
          )}
        </section>

        {/* Phase 0.11.1：删除语义——普通图仅淘汰(REJECT)；仅 REJECT 图才永久物理删除 */}
        <section className="gal-detail-section gal-detail-section--danger" aria-labelledby="gal-danger-title">
          <h3 id="gal-danger-title" className="gal-section-title">危险区</h3>
          <div className="gal-actions">
            <Button
              size="sm" variant="danger"
              disabled={busy}
              onClick={() => { onReviewStart(displayStatus); void run(() => imageApi.setStatus(image.id, { status: 'REJECT' }), '已淘汰') }}
            >
              淘汰 (R)
            </Button>
          </div>
          <h4 className="gal-danger-title">{displayStatus === 'REJECT' ? '永久删除此废片' : '淘汰图片'}</h4>
          {displayStatus !== 'REJECT' ? (
            <>
              <p className="muted">仅将状态置为 REJECT（文件保留），之后可在「清理废片」中永久删除。</p>
              <Button size="sm" variant="danger" disabled={busy} onClick={() => void softReject()}>
                {busy ? '处理中…' : '淘汰此图'}
              </Button>
            </>
          ) : (
            <>
              <p className="muted">删除前会检查引用；被 Prompt / 素材 / 配方引用的图片将被保护，不会删除。</p>
              {!deleteArm ? (
                <Button size="sm" variant="danger" disabled={busy} onClick={() => setDeleteArm(true)}>
                  永久删除此废片
                </Button>
              ) : (
                <div className="gal-actions">
                  <Button size="sm" variant="danger" disabled={busy} onClick={() => void deleteImage()}>
                    {busy ? '处理中…' : '确认删除（不可恢复）'}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => setDeleteArm(false)}>
                    取消
                  </Button>
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </Drawer>
  )
}
