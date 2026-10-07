import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ApiRequestError, assetApi, imageApi, jobApi } from '../../api/client'
import { formatDateTime } from '../../utils/format'
import {
  ASSET_TYPES,
  IMAGE_SOURCE_LABEL,
  REVIEW_STATUS_LABEL,
  imageContentUrl,
  shortJobId,
  type AssetType,
  type ImageDTO,
  type JobDTO,
} from '../../types/workbench'

/**
 * 图库（Phase 2C 规范 §四十五-§四十九）：
 * 顶部筛选（未审核 / 保留 / 收藏 / 淘汰）+ 图片 Grid + 右侧 Detail Drawer，
 * 支持按 Job 查看、审核 / 收藏、Image → Workbench、从图库创建素材。
 */

type Filter = 'ALL' | 'UNREVIEWED' | 'KEPT' | 'FAVORITE' | 'REJECTED'
type ViewMode = 'flat' | 'group'

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'ALL', label: '全部' },
  { key: 'UNREVIEWED', label: '未审核' },
  { key: 'KEPT', label: '保留' },
  { key: 'FAVORITE', label: '收藏' },
  { key: 'REJECTED', label: '淘汰' },
]

interface JobSummary {
  job_id: string
  total: number
  unreviewed: number
  kept: number
  rejected: number
  favorites: number
}

export default function GalleryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const jobFilter = searchParams.get('job')
  const [filter, setFilter] = useState<Filter>('ALL')
  const [view, setView] = useState<ViewMode>('flat')
  const [items, setItems] = useState<ImageDTO[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [detail, setDetail] = useState<ImageDTO | null>(null)
  const [groups, setGroups] = useState<{ job: JobDTO; summary: JobSummary }[]>([])
  const [groupsLoading, setGroupsLoading] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    imageApi
      .list({
        job_id: jobFilter,
        review_status:
          filter === 'UNREVIEWED' || filter === 'KEPT' || filter === 'REJECTED' ? filter : null,
        favorite: filter === 'FAVORITE' ? true : null,
        limit: 200,
      })
      .then((page) => {
        setItems(page.items)
        setTotal(page.total)
      })
      .catch((err: unknown) => setError(err instanceof ApiRequestError ? err.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [filter, jobFilter])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (view !== 'group' || jobFilter) return
    let cancelled = false
    setGroupsLoading(true)
    jobApi
      .list({ limit: 50 })
      .then(async (page) => {
        const candidates = page.items.filter((job) => job.completed_count > 0).slice(0, 20)
        const summaries = await Promise.all(
          candidates.map((job) => imageApi.jobSummary(job.id).catch(() => null)),
        )
        if (cancelled) return
        setGroups(
          candidates.flatMap((job, index) => {
            const summary = summaries[index]
            return summary ? [{ job, summary }] : []
          }),
        )
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : '无法加载任务分组')
      })
      .finally(() => {
        if (!cancelled) setGroupsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [view, jobFilter])

  function applyJobFilter(jobId: string | null): void {
    const next = new URLSearchParams(searchParams)
    if (jobId) next.set('job', jobId)
    else next.delete('job')
    setSearchParams(next)
  }

  function handleUpdated(updated: ImageDTO): void {
    setItems((previous) => previous.map((item) => (item.id === updated.id ? updated : item)))
    setDetail((current) => (current && current.id === updated.id ? updated : current))
  }

  return (
    <section className="page page--wide">
      <div className="tabs" role="tablist" aria-label="图库筛选">
        {FILTERS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={filter === key}
            className={`tabs__item${filter === key ? ' tabs__item--active' : ''}`}
            onClick={() => setFilter(key)}
          >
            {label}
          </button>
        ))}
        <span className="toolbar__spacer" />
        <button
          type="button"
          className={`tabs__item${view === 'group' ? ' tabs__item--active' : ''}`}
          onClick={() => setView(view === 'group' ? 'flat' : 'group')}
        >
          按任务查看
        </button>
      </div>

      {jobFilter && (
        <div className="toolbar">
          <span className="badge badge--mode">任务筛选：{shortJobId(jobFilter)}</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => applyJobFilter(null)}>
            清除筛选
          </button>
        </div>
      )}

      {error && <p className="notice notice--error">{error}</p>}

      {/* ===== 按任务分组（§四十九） ===== */}
      {view === 'group' && !jobFilter && (
        <div className="job-group-list">
          {groupsLoading && <p className="muted">加载中…</p>}
          {!groupsLoading && groups.length === 0 && (
            <p className="muted">还没有完成过的生成任务。</p>
          )}
          {groups.map(({ job, summary }) => (
            <button
              key={job.id}
              type="button"
              className="job-group card card--clickable"
              onClick={() => applyJobFilter(job.id)}
            >
              <div className="job-group__head">
                <span className="job-group__id">{shortJobId(job.id)}</span>
                <span className="muted">{summary.total} 张 · {formatDateTime(job.created_at)}</span>
              </div>
              <p className="job-group__title">
                {job.positive_prompt_snapshot.trim().slice(0, 42) || '（无 Prompt）'}
              </p>
              <p className="job-group__counts muted">
                未审核 {summary.unreviewed} · 保留 {summary.kept} · 收藏 {summary.favorites} · 淘汰{' '}
                {summary.rejected}
              </p>
            </button>
          ))}
        </div>
      )}

      {/* ===== 图片 Grid ===== */}
      {(view === 'flat' || jobFilter) && (
        <>
          {loading && <p className="muted">加载中…</p>}
          {!loading && items.length === 0 && (
            <div className="empty-state">
              <h1 className="empty-state__title">还没有图片</h1>
              <p className="empty-state__desc">
                在生成工作台创建任务后，生成的图片会逐张进入这里。
              </p>
            </div>
          )}
          <p className="muted">共 {total} 张</p>
          <div className="gallery-grid">
            {items.map((image) => (
              <button
                key={image.id}
                type="button"
                className="gallery-card"
                onClick={() => setDetail(image)}
                title={`${shortJobId(image.job_id ?? '')} · ${REVIEW_STATUS_LABEL[image.review_status]}`}
              >
                <img
                  className="gallery-card__img"
                  src={imageContentUrl(image.id)}
                  alt=""
                  loading="lazy"
                />
                <span className="gallery-card__badges">
                  {image.favorite && <span className="status-chip status-chip--favorite">★</span>}
                  {image.review_status !== 'UNREVIEWED' && (
                    <span className={`status-chip status-chip--${image.review_status.toLowerCase()}`}>
                      {REVIEW_STATUS_LABEL[image.review_status]}
                    </span>
                  )}
                </span>
              </button>
            ))}
          </div>
        </>
      )}

      {detail && (
        <GalleryDetailDrawer
          image={detail}
          onClose={() => setDetail(null)}
          onUpdated={handleUpdated}
        />
      )}
    </section>
  )
}

// ===== 详情抽屉（§四十六-§四十八） =====

interface DetailDrawerProps {
  image: ImageDTO
  onClose: () => void
  onUpdated: (image: ImageDTO) => void
}

function GalleryDetailDrawer({ image, onClose, onUpdated }: DetailDrawerProps) {
  const navigate = useNavigate()
  const [job, setJob] = useState<JobDTO | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [assetType, setAssetType] = useState<AssetType>('face')
  const [assetName, setAssetName] = useState(`图库-${image.id.replace(/^img_/, '').slice(0, 8)}`)

  useEffect(() => {
    if (!image.job_id) return
    let cancelled = false
    jobApi
      .get(image.job_id)
      .then((detail) => {
        if (!cancelled) setJob(detail)
      })
      .catch(() => {
        // 任务信息缺失不阻塞图片查看
      })
    return () => {
      cancelled = true
    }
  }, [image.job_id])

  async function run(action: () => Promise<ImageDTO>, okText: string): Promise<void> {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      onUpdated(await action())
      setMessage(okText)
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  function openInWorkbench(useSeed: boolean): void {
    setError(null)
    imageApi
      .workbench(image.id)
      .then((result) => {
        const snapshot = { ...result.snapshot }
        if (useSeed && image.seed !== null) {
          snapshot.seed = image.seed
          snapshot.seed_mode = 'fixed'
        }
        onClose()
        navigate('/generate', { state: { workbench: snapshot } })
      })
      .catch((err: unknown) =>
        setError(err instanceof ApiRequestError ? err.message : '无法恢复到工作台'),
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

  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="drawer drawer--wide"
        role="dialog"
        aria-modal="true"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drawer__header">
          <h3 className="drawer__title">
            图片详情
            {image.favorite && <span title="已收藏"> ★</span>}
          </h3>
          <button type="button" className="btn btn--ghost btn--sm" onClick={onClose} aria-label="关闭">
            ✕
          </button>
        </header>

        <div className="gallery-detail__preview">
          <img src={imageContentUrl(image.id)} alt="" />
        </div>

        <div className="drawer__meta-actions">
          <button
            type="button"
            className={`btn btn--sm${image.review_status === 'KEPT' ? ' btn--primary' : ''}`}
            disabled={busy}
            onClick={() => void run(() => imageApi.review(image.id, 'KEPT'), '已保留')}
          >
            保留
          </button>
          <button
            type="button"
            className={`btn btn--sm${image.review_status === 'REJECTED' ? ' btn--primary' : ''}`}
            disabled={busy}
            onClick={() => void run(() => imageApi.review(image.id, 'REJECTED'), '已淘汰')}
          >
            淘汰
          </button>
          {image.review_status !== 'UNREVIEWED' && (
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              disabled={busy}
              onClick={() => void run(() => imageApi.review(image.id, 'UNREVIEWED'), '已恢复为未审核')}
            >
              取消审核
            </button>
          )}
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            disabled={busy}
            onClick={() => void run(() => imageApi.favorite(image.id, !image.favorite), image.favorite ? '已取消收藏' : '已收藏')}
          >
            {image.favorite ? '★ 已收藏' : '☆ 收藏'}
          </button>
        </div>

        <div className="drawer__meta-actions">
          <button
            type="button"
            className="btn btn--primary btn--sm"
            disabled={!image.job_id}
            onClick={() => openInWorkbench(false)}
          >
            在生成工作台中打开
          </button>
          <button
            type="button"
            className="btn btn--sm"
            disabled={!image.job_id || image.seed === null}
            onClick={() => openInWorkbench(true)}
          >
            使用此图 Seed
          </button>
        </div>

        {message && <p className="notice notice--ok" role="status">{message}</p>}
        {error && <p className="notice notice--error">{error}</p>}

        <dl className="asset-detail__fields">
          <dt>Prompt</dt>
          <dd><pre className="asset-detail__prompt">{job?.positive_prompt_snapshot || '（不可用）'}</pre></dd>
          <dt>Negative</dt>
          <dd><pre className="asset-detail__prompt">{job?.negative_prompt_snapshot || '（无）'}</pre></dd>
          <dt>Seed</dt>
          <dd>{image.seed ?? '—'}</dd>
          <dt>任务</dt>
          <dd>{image.job_id ? shortJobId(image.job_id) : '—（导入图片）'}</dd>
          <dt>来源</dt>
          <dd>{IMAGE_SOURCE_LABEL[image.source] ?? image.source}</dd>
          <dt>时间</dt>
          <dd>{formatDateTime(image.created_at)}</dd>
          <dt>尺寸</dt>
          <dd>{image.width} × {image.height}</dd>
          <dt>审核</dt>
          <dd>{REVIEW_STATUS_LABEL[image.review_status]}</dd>
        </dl>

        {/* ===== 从图库创建素材（§四十八：独立素材文件 + source_image_id） ===== */}
        <section className="asset-edit">
          <h4 className="version-history__title">创建素材（独立资产文件，图片以后被清理不影响素材）</h4>
          <div className="field">
            <label className="field__label" htmlFor="gallery-asset-type">类型</label>
            <select
              id="gallery-asset-type"
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
            <label className="field__label" htmlFor="gallery-asset-name">名称</label>
            <input
              id="gallery-asset-name"
              className="input"
              value={assetName}
              onChange={(event) => setAssetName(event.target.value)}
            />
          </div>
          <div className="modal__actions">
            <button
              type="button"
              className="btn btn--primary btn--sm"
              disabled={busy || !assetName.trim()}
              onClick={() => void createAsset()}
            >
              创建素材
            </button>
          </div>
        </section>
      </aside>
    </div>
  )
}