// 历史 Tab：来源 = jobs（不另建 History 表）。任务族两级归组：原任务 + 续跑任务；
// Drawer 提供完整 Prompt / 结构化字段 / 尺寸 / Seed / Workflow stages / 版本 / 错误 /
// 生成图片，以及“在生成工作台打开 / 在图库查看 / 继续剩余图片”。
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiRequestError, historyApi, imageApi, jobApi, moduleApi } from '../../api/client'
import {
  Badge,
  Button,
  Drawer,
  Select,
  StatusBadge,
  Tabs,
} from '../../components/ui'
import { formatDateTime } from '../../utils/format'
import {
  HISTORY_BUCKET_LABEL,
  JOB_SOURCE_LABEL,
  MODULE_LABEL,
  STRUCTURED_FIELDS,
  imageContentUrl,
  shortJobId,
  type HistoryBucket,
  type HistoryEntryDTO,
  type ImageDTO,
  type JobDTO,
  type WorkbenchSnapshot,
  type WorkflowModuleRef,
} from '../../types/workbench'

const SOURCE_FILTERS: { key: string | null; label: string }[] = [
  { key: null, label: '全部来源' },
  { key: 'web', label: 'Web' },
  { key: 'resume', label: '续跑' },
  { key: 'agent', label: 'Agent' },
  { key: 'doubao', label: 'Doubao' },
]

const RESUMABLE_STATUSES = ['FAILED', 'CANCELLED', 'INTERRUPTED']

function pipelineText(job: JobDTO): string {
  const modules = job.workflow_snapshot?.modules ?? []
  if (modules.length > 0) {
    return modules.map((module) => MODULE_LABEL[module.module_id] ?? module.module_id).join(' → ')
  }
  if (job.module_id) return MODULE_LABEL[job.module_id] ?? job.module_id
  return '基础生成'
}

function canResumeRemaining(job: JobDTO): boolean {
  return RESUMABLE_STATUSES.includes(job.status) && job.completed_count < job.requested_count
}

/** Task9：从历史 Job 恢复 → 携带完整执行身份（含双指纹） */
function snapshotFromJob(job: JobDTO): WorkbenchSnapshot {
  const modules = (job.workflow_snapshot?.modules ?? []) as WorkflowModuleRef[]
  const identity: WorkflowModuleRef[] = modules.length > 0
    ? modules
    : job.module_id
      ? [{
          module_id: job.module_id,
          module_version: job.module_version ?? undefined,
          provider: job.provider ?? undefined,
          binding_version: job.binding_version ?? undefined,
          workflow_hash: job.workflow_hash,
          binding_hash: job.binding_hash,
        }]
      : job.workbench_snapshot.workflow_modules
  return { ...job.workbench_snapshot, workflow_modules: identity }
}

export function HistoryTab() {
  const [bucket, setBucket] = useState<HistoryBucket>('all')
  const [source, setSource] = useState<string | null>(null)
  const [items, setItems] = useState<HistoryEntryDTO[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [detailJob, setDetailJob] = useState<JobDTO | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    historyApi
      .list({ bucket, source, limit: 100 })
      .then((page) => {
        setItems(page.items)
        setTotal(page.total)
      })
      .catch((err: unknown) => setError(err instanceof ApiRequestError ? err.message : '加载历史失败'))
      .finally(() => setLoading(false))
  }, [bucket, source])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div>
      <div className="pp-toolbar">
        <Tabs
          ariaLabel="历史筛选"
          active={bucket}
          onChange={(key) => setBucket(key as HistoryBucket)}
          items={(Object.keys(HISTORY_BUCKET_LABEL) as HistoryBucket[]).map((key) => ({
            key,
            label: HISTORY_BUCKET_LABEL[key],
          }))}
        />
        <span className="pp-toolbar__spacer" />
        <Select
          aria-label="按来源筛选"
          value={source ?? ''}
          onChange={(event) => setSource(event.target.value || null)}
          options={SOURCE_FILTERS.map(({ key, label }) => ({ value: key ?? '', label }))}
        />
      </div>

      {error && <p className="ds-notice ds-notice--error">{error}</p>}
      {loading && <p className="muted">加载中…</p>}

      {!loading && items.length === 0 && (
        <div className="pp-empty">
          <h2 className="pp-empty__title">暂无生成历史</h2>
          <p className="muted">在工作台提交生成任务后，历史会自动记录在这里。</p>
        </div>
      )}

      {!loading && items.length > 0 && <p className="pp-count">共 {total} 个任务</p>}
      <div className="pp-hist-list">
        {items.map((entry) => (
          <div key={entry.root_job_id} className="pp-family">
            <HistoryJobCard job={entry.root} onOpen={setDetailJob} />
            {entry.resumes.length > 0 && (
              <div className="pp-family__resumes">
                {entry.resumes.map((resume) => (
                  <HistoryJobCard key={resume.id} job={resume} isResume onOpen={setDetailJob} />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {detailJob && (
        <HistoryDetailDrawer
          job={detailJob}
          onClose={() => setDetailJob(null)}
          onResumed={load}
        />
      )}
    </div>
  )
}

function HistoryJobCard({ job, isResume, onOpen }: {
  job: JobDTO
  isResume?: boolean
  onOpen: (job: JobDTO) => void
}) {
  const excerpt = job.positive_prompt_snapshot.trim() || '（无 Prompt）'
  return (
    <button
      type="button"
      className={`pp-hist-card${isResume ? ' pp-hist-card--resume' : ''}`}
      onClick={() => onOpen(job)}
    >
      <div className="pp-hist-card__head">
        <StatusBadge status={job.status} />
        <Badge tone="accent">{JOB_SOURCE_LABEL[job.source] ?? job.source}</Badge>
        {isResume && <Badge tone="accent">续跑</Badge>}
        <span className="pp-toolbar__spacer" />
        <span className="muted">{shortJobId(job.id)} · {formatDateTime(job.created_at)}</span>
      </div>
      <p className="pp-hist-card__title" title={excerpt}>
        {excerpt.length > 72 ? `${excerpt.slice(0, 72)}…` : excerpt}
      </p>
      <p className="pp-hist-card__meta muted">
        {job.job_kind === 'process' ? '处理型' : '生成'} · 完成 {job.completed_count} / {job.requested_count} 张 ·{' '}
        {pipelineText(job)}
        {canResumeRemaining(job) ? ' · 有剩余可续跑' : ''}
      </p>
    </button>
  )
}

function HistoryDetailDrawer({ job, onClose, onResumed }: {
  job: JobDTO
  onClose: () => void
  onResumed: () => void
}) {
  const navigate = useNavigate()
  const [images, setImages] = useState<ImageDTO[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    imageApi
      .list({ job_id: job.id, limit: 200 })
      .then((page) => { if (!cancelled) setImages(page.items) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [job.id])

  /** 尺寸语义：explicit 显示 generation_settings；size_mode=input 显示跟随输入图 */
  const [sizeText, setSizeText] = useState('—')

  useEffect(() => {
    let cancelled = false
    const settings = job.generation_settings as { width?: number; height?: number }
    const explicit =
      settings.width && settings.height ? `${settings.width} × ${settings.height}` : '—'
    setSizeText(explicit)

    const stage0 = job.stages?.[0]
    const inputId = stage0?.items.find((item) => item.input_image_id)?.input_image_id ?? null
    if (!stage0 || !inputId) {
      return () => { cancelled = true }
    }
    moduleApi
      .list()
      .then((modules) => {
        if (cancelled) return
        const capabilities = modules.find((module) => module.module_id === stage0.module_id)
        if (capabilities?.size_mode !== 'input') return
        imageApi
          .get(inputId)
          .then((image) => {
            if (!cancelled) setSizeText(`跟随输入图 ${image.width}×${image.height}`)
          })
          .catch(() => { if (!cancelled) setSizeText('跟随输入图') })
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [job])

  const seeds = job.items.map((item) => item.seed).filter((seed): seed is number => seed !== null)
  const structuredFields = STRUCTURED_FIELDS.filter(({ key }) => job.structured_prompt[key]?.trim())
  const resumable = canResumeRemaining(job)

  function openInWorkbench(): void {
    onClose()
    navigate('/generate', { state: { workbench: snapshotFromJob(job) } })
  }

  function viewInGallery(): void {
    onClose()
    navigate(`/gallery?job=${job.id}`)
  }

  async function resumeRemaining(): Promise<void> {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const created = await jobApi.resumeRemaining(job.id)
      setMessage(`已创建续跑任务 ${shortJobId(created.id)}（继承原 Workflow 身份）`)
      onResumed()
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : '续跑失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Drawer open onClose={onClose} width="wide" title={`任务详情 ${shortJobId(job.id)}`}>
      <div className="pp-toolbar">
        <StatusBadge status={job.status} />
        <Badge tone="accent">{JOB_SOURCE_LABEL[job.source] ?? job.source}</Badge>
        <span className="muted">{formatDateTime(job.created_at)}</span>
      </div>

      <div className="pp-toolbar">
        <Button size="sm" variant="primary" onClick={openInWorkbench}>
          在生成工作台打开
        </Button>
        <Button size="sm" variant="secondary" onClick={viewInGallery}>
          在图库查看
        </Button>
        <Button
          size="sm" variant="secondary"
          disabled={!resumable || busy}
          title={resumable ? undefined : '仅失败/取消/中断且仍有未完成图片时可续跑'}
          onClick={() => void resumeRemaining()}
        >
          {busy ? '提交中…' : '继续剩余图片'}
        </Button>
      </div>

      {message && <p className="ds-notice ds-notice--success" role="status">{message}</p>}
      {error && <p className="ds-notice ds-notice--error">{error}</p>}

      <dl className="pp-fields">
        <dt>完整 Prompt</dt>
        <dd><pre>{job.positive_prompt_snapshot || '（无）'}</pre></dd>
        <dt>Negative</dt>
        <dd><pre>{job.negative_prompt_snapshot || '（无）'}</pre></dd>
        {structuredFields.length > 0 && (
          <>
            <dt>结构化 Prompt</dt>
            <dd>
              {structuredFields.map(({ key, label }) => (
                <div key={key}>
                  <span className="muted">{label}：</span>
                  {job.structured_prompt[key]}
                </div>
              ))}
            </dd>
          </>
        )}
        <dt>尺寸</dt>
        <dd>{sizeText}</dd>
        <dt>Seed</dt>
        <dd>{seeds.length > 0 ? seeds.join(', ') : '—（不使用 Seed）'}</dd>
        <dt>数量</dt>
        <dd>完成 {job.completed_count} / {job.requested_count} 张</dd>
        {job.resume_of_job_id && (
          <>
            <dt>续跑自</dt>
            <dd>{shortJobId(job.resume_of_job_id)}</dd>
          </>
        )}
        {job.error_message && (
          <>
            <dt>错误</dt>
            <dd>{job.error_type}：{job.error_message}</dd>
          </>
        )}
      </dl>

      <section className="pp-versions">
        <h4 className="pp-versions__title">Workflow</h4>
        <ul className="pp-stages">
          {job.stages.map((stage) => (
            <li key={stage.id} className="pp-stages__item">
              <span>
                {stage.stage_index + 1}. {MODULE_LABEL[stage.module_id] ?? stage.module_id} ·{' '}
                {stage.status} · {stage.completed_count} / {stage.total_count}
              </span>
              <span className="muted">
                {stage.module_version} / binding {stage.binding_version ?? '—'}
                {stage.workflow_hash ? ` · wf ${stage.workflow_hash.slice(0, 8)}` : ''}
                {stage.binding_hash ? ` · bd ${stage.binding_hash.slice(0, 8)}` : ''}
              </span>
            </li>
          ))}
        </ul>
      </section>

      {images.length > 0 && (
        <section className="pp-versions">
          <h4 className="pp-versions__title">生成图片（{images.length}）</h4>
          <div className="pp-thumbs">
            {images.map((image) => (
              <div key={image.id} className="pp-thumbs__item">
                <img src={imageContentUrl(image.id)} alt="" loading="lazy" />
                <span className="pp-thumbs__badge">
                  {image.kind === 'upscaled' ? 'HD' : image.kind === 'original' ? '原图' : '处理'}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </Drawer>
  )
}
