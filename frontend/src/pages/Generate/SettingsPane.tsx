import { useState, type DragEvent, type ReactNode } from 'react'
import {
  hasUpscaleModule,
  isImageCapablePrimary,
  setCount,
  setPrimaryModule,
  setPrimaryModuleConfig,
  setSeed,
  setSize,
  setUpscaleEnabled,
  snapshotFromState,
  useWorkbench,
} from '../../stores/workbenchStore'
import {
  activeJob,
  cancelJob,
  pauseJob,
  reorderQueue,
  resumeJob,
  resumeQueue,
  resumeRemaining,
  submitGeneration,
  useJobStore,
} from '../../stores/jobStore'
import {
  Button,
  Checkbox,
  Field,
  Input,
  ProgressBar,
  Select,
  Slider,
  StatusBadge,
} from '../../components/ui'
import {
  MODULE_LABEL,
  STAGE_LABEL,
  shortJobId,
  type JobDTO,
  type ModuleParameterDTO,
} from '../../types/workbench'
import { overallProgress, stageProgressLines } from '../../utils/jobProgress'
import { Pane } from './Pane'

/** 右栏（§五十一、§五十三、§五十四）：真实 Engine 状态 / 参数 / 生成按钮 / 当前任务 / 队列。 */
export function SettingsPane({ imageGenAvailable }: { imageGenAvailable: boolean | null }) {
  const state = useWorkbench()
  const store = useJobStore()
  const [widthText, setWidthText] = useState(String(state.width))
  const [heightText, setHeightText] = useState(String(state.height))
  const [notice, setNotice] = useState<string | null>(null)
  const [dragJobId, setDragJobId] = useState<string | null>(null)

  const job = activeJob(store)
  const engineOffline = store.engineLoaded && store.engine !== null && !store.engine.online
  const hasPrompt =
    state.promptMode === 'full'
      ? state.fullPrompt.trim().length > 0
      : Object.values(state.structured).some((value) => value.trim().length > 0)
  const upscaleEnabled = hasUpscaleModule(state.workflowModules)
  const primaryModule = state.workflowModules[0]?.module_id ?? 'basic_generate'
  const primaryCapabilities =
    state.moduleCatalog.find((module) => module.module_id === primaryModule) ?? null
  const primaryTitle =
    primaryCapabilities?.title ?? MODULE_LABEL[primaryModule] ?? primaryModule
  const primaryCandidates = state.moduleCatalog.filter((module) =>
    module.available &&
    (state.mode === 'text'
      ? !module.input_required
      : module.input_required && module.output_kind === 'processed'),
  )
  const configurableParams = (primaryCapabilities?.parameters ?? []).filter(
    (param) => param.configurable,
  )
  const followsInputSize = primaryCapabilities?.size_mode === 'input'
  const primaryImageCapable = state.mode !== 'image' || isImageCapablePrimary(state)
  const inputImage = state.inputImages[0] ?? null
  const imageGateBlocked = state.mode === 'image' && (imageGenAvailable !== true || !primaryImageCapable)
  const generateHint = store.submitting
    ? undefined
    : engineOffline
      ? 'Engine 离线，无法提交'
      : !hasPrompt
        ? '请先填写 Prompt'
        : imageGateBlocked
          ? imageGenAvailable !== true
            ? '图片生成：尚未配置可用工作流'
            : '图片生成：当前工作流不接受输入图片'
          : state.mode === 'image' && !inputImage
            ? '请先选择输入图片'
            : inputImage?.missing
              ? '输入图片已丢失，请移除后重新选择'
              : undefined

  function commitSize(): void {
    const width = clampDimension(widthText)
    const height = clampDimension(heightText)
    setWidthText(String(width))
    setHeightText(String(height))
    setSize(width, height)
  }

  async function handleGenerate(queueMode: 'normal' | 'next'): Promise<void> {
    setNotice(null)
    const created = await submitGeneration(snapshotFromState(), queueMode)
    if (!created) return
    if (created.idempotent_replay) {
      setNotice(`相同请求已提交过，已定位到原任务 ${shortJobId(created.id)}`)
    } else {
      setNotice(
        created.disk_space === 'warning'
          ? `已加入队列 ${shortJobId(created.id)}（磁盘空间偏低，建议清理）`
          : `已加入队列 ${shortJobId(created.id)}`,
      )
    }
  }

  function moveBefore(sourceId: string, targetId: string): void {
    const ids = (store.queue?.queued ?? []).map((item) => item.id)
    const from = ids.indexOf(sourceId)
    const to = ids.indexOf(targetId)
    if (from < 0 || to < 0 || from === to) return
    const [moved] = ids.splice(from, 1)
    ids.splice(to, 0, moved)
    void reorderQueue(ids)
  }

  function moveToFront(jobId: string): void {
    const ids = (store.queue?.queued ?? []).map((item) => item.id)
    if (ids.indexOf(jobId) <= 0) return
    void reorderQueue([jobId, ...ids.filter((id) => id !== jobId)])
  }

  const queued = store.queue?.queued ?? []
  const paused = store.queue?.paused ?? []
  const disabled = store.submitting || generateHint !== undefined

  return (
    <Pane title="生成配置">
      {/* ===== 真实 Engine 状态 ===== */}
      <Field label="引擎">
        <span
          className={`engine-state engine-state--${
            store.engineLoaded ? (store.engine?.online ? 'online' : 'offline') : 'checking'
          }`}
          title={store.engine?.detail}
        >
          <span className="engine-state__dot" aria-hidden="true" />
          {store.engine?.online
            ? `${store.engine.engine_name} ${store.engine.engine_version}`
            : store.engineLoaded
              ? '离线'
              : '检测中'}
        </span>
      </Field>

      {/* ===== 工作流 ===== */}
      <Field label="工作流">
        {primaryCandidates.length > 1 ? (
          <Select
            id="primary-module"
            value={primaryModule}
            onChange={(event) => setPrimaryModule(event.target.value)}
            options={primaryCandidates.map((module) => ({
              value: module.module_id,
              label: module.title || MODULE_LABEL[module.module_id] || module.module_id,
            }))}
          />
        ) : (
          <p className="wb-static">① {primaryTitle}</p>
        )}
        <Checkbox
          checked={upscaleEnabled}
          onChange={(event) => setUpscaleEnabled(event.target.checked)}
          label="② 高清放大"
        />
        {upscaleEnabled && (
          <p className="muted">原图全部完成后，依次生成高清图（原图与高清保持父子关系）。</p>
        )}
      </Field>

      {/* ===== 模块参数 ===== */}
      {configurableParams.map((param) => (
        <ModuleParameterField
          key={param.name}
          param={param}
          value={state.workflowModules[0]?.config?.[param.name]}
          onChange={(value) => setPrimaryModuleConfig({ [param.name]: value })}
        />
      ))}

      {/* ===== 尺寸 ===== */}
      {followsInputSize ? (
        <Field label="尺寸"><p className="wb-static">跟随输入图（无需设置宽高）</p></Field>
      ) : (
        <div className="size-row">
          <Field label="宽度 (px)">
            <Input
              type="number" min={64} max={4096} step={64}
              value={widthText}
              onChange={(event) => setWidthText(event.target.value)}
              onBlur={commitSize}
            />
          </Field>
          <Field label="高度 (px)">
            <Input
              type="number" min={64} max={4096} step={64}
              value={heightText}
              onChange={(event) => setHeightText(event.target.value)}
              onBlur={commitSize}
            />
          </Field>
        </div>
      )}

      <Field label="数量">
        <Select
          value={state.count}
          onChange={(event) => setCount(Number(event.target.value))}
          options={[1, 2, 4, 6, 8].map((n) => ({ value: n, label: String(n) }))}
        />
      </Field>

      <Field label="Seed">
        {state.seedMode === 'fixed' && state.seed !== null ? (
          <p className="wb-static">
            固定 {state.seed}
            <span className="muted">（单张精确复现；选择数量 &gt; 1 将自动切回随机）</span>
            <Button size="xs" variant="ghost" onClick={() => setSeed(null)}>恢复随机</Button>
          </p>
        ) : (
          <p className="wb-static">随机（每张独立）</p>
        )}
      </Field>

      {imageGateBlocked && (
        <p className="ds-notice ds-notice--warning">
          {imageGenAvailable !== true
            ? '图片生成：尚未配置可用工作流（等待模型方案确认）。可先选择输入图片并保存配方。'
            : '图片生成：当前工作流不接受输入图片，请切换到可用的图片生成工作流（如“图生图”）。'}
        </p>
      )}

      <div className="wb-actions">
        <Button
          variant="primary" size="lg" className="wb-actions__main"
          disabled={disabled} title={generateHint}
          onClick={() => void handleGenerate('normal')}
        >
          {store.submitting ? '提交中…' : '生成'}
        </Button>
        <Button
          variant="secondary" size="sm"
          disabled={disabled} title={generateHint}
          onClick={() => void handleGenerate('next')}
        >
          优先生成（插队）
        </Button>
      </div>

      {store.lastError && <p className="ds-notice ds-notice--error" role="alert">{store.lastError}</p>}
      {notice && <p className="ds-notice ds-notice--success" role="status">{notice}</p>}

      {job && <CurrentJobCard job={job} busy={store.busyJobId === job.id} />}

      {/* ===== 队列 ===== */}
      <section className="wb-queue">
        <h3 className="wb-queue__title">队列</h3>
        {store.queue?.worker.queue_paused && (
          <div className="ds-notice ds-notice--warning" role="alert">
            <p>队列已自动暂停：{store.queue.worker.queue_paused_reason ?? '系统性失败'}</p>
            <Button size="sm" onClick={() => void resumeQueue()}>恢复队列</Button>
          </div>
        )}
        {queued.length === 0 && paused.length === 0 && <p className="muted">暂无等待任务</p>}
        <ul className="wb-queue-list">
          {queued.map((item, index) => (
            <QueueRow
              key={item.id}
              job={item}
              draggable
              dragging={dragJobId === item.id}
              onDragStart={() => setDragJobId(item.id)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => {
                if (dragJobId) moveBefore(dragJobId, item.id)
                setDragJobId(null)
              }}
              onDragEnd={() => setDragJobId(null)}
              actions={
                <>
                  {index > 0 && (
                    <Button size="xs" variant="ghost" onClick={() => moveToFront(item.id)}>优先</Button>
                  )}
                  <Button size="xs" variant="ghost" onClick={() => void pauseJob(item.id)}>暂停</Button>
                  <Button size="xs" variant="ghost" onClick={() => void cancelJob(item.id)}>取消</Button>
                </>
              }
            />
          ))}
          {paused.map((item) => (
            <QueueRow
              key={item.id}
              job={item}
              actions={
                <>
                  <Button size="xs" variant="ghost" onClick={() => void resumeJob(item.id)}>继续</Button>
                  <Button size="xs" variant="ghost" onClick={() => void cancelJob(item.id)}>取消</Button>
                </>
              }
            />
          ))}
        </ul>
      </section>
    </Pane>
  )
}

// ===== 当前任务卡片 =====

function CurrentJobCard({ job, busy }: { job: JobDTO; busy: boolean }) {
  const runningItem = job.items.find((item) => item.status === 'RUNNING')
  const progress = overallProgress(job)
  const stageLines = stageProgressLines(job)
  const progressText =
    job.status === 'RUNNING' && runningItem
      ? `第 ${runningItem.item_index + 1} 张 · ${progress}%`
      : `已完成 ${job.completed_count} / ${job.requested_count}`
  const moduleLabel =
    stageLines.length > 0
      ? job.stages.map((stage) => MODULE_LABEL[stage.module_id] ?? stage.module_id).join(' → ')
      : MODULE_LABEL[job.module_id ?? ''] ?? job.module_id ?? '基础生成'
  const excerpt = job.positive_prompt_snapshot.trim() || '（无 Prompt）'
  const canResumeRemaining =
    ['FAILED', 'CANCELLED', 'INTERRUPTED'].includes(job.status) &&
    job.completed_count < job.requested_count

  return (
    <section className="wb-job">
      <div className="wb-job__head">
        <StatusBadge status={job.status} />
        <span className="muted">{shortJobId(job.id)}</span>
      </div>
      <p className="wb-job__title" title={excerpt}>
        {excerpt.length > 28 ? `${excerpt.slice(0, 28)}…` : excerpt}
      </p>
      <ProgressBar value={progress / 100} ariaLabel="任务进度" />
      {stageLines.length > 0 ? (
        <ul className="wb-stages" aria-label="分阶段进度">
          {stageLines.map((line) => (
            <li key={line.key} className={line.done ? 'wb-stages__done' : undefined}>
              {line.text}
            </li>
          ))}
        </ul>
      ) : (
        <p className="wb-job__meta">
          {progressText}
          {runningItem?.current_stage ? ` · ${STAGE_LABEL[runningItem.current_stage] ?? runningItem.current_stage}` : ''}
        </p>
      )}
      <p className="wb-job__meta">{moduleLabel}</p>
      {job.resume_of_job_id && <p className="muted">续跑自 {shortJobId(job.resume_of_job_id)}</p>}
      {job.error_message && (
        <p className="ds-notice ds-notice--error">{job.error_type}：{job.error_message}</p>
      )}

      <div className="wb-job__actions">
        {job.status === 'RUNNING' && !job.pause_requested && (
          <Button size="sm" disabled={busy} onClick={() => void pauseJob(job.id)}>暂停</Button>
        )}
        {job.status === 'RUNNING' && job.pause_requested && (
          <span className="muted">将在当前图完成后暂停…</span>
        )}
        {job.status === 'QUEUED' && (
          <Button size="sm" disabled={busy} onClick={() => void pauseJob(job.id)}>暂停</Button>
        )}
        {job.status === 'PAUSED' && (
          <Button size="sm" disabled={busy} onClick={() => void resumeJob(job.id)}>继续</Button>
        )}
        {job.status === 'RUNNING' && job.cancel_requested && <span className="muted">正在取消…</span>}
        {['QUEUED', 'RUNNING', 'PAUSED'].includes(job.status) && !job.cancel_requested && (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => void cancelJob(job.id)}>取消</Button>
        )}
        {canResumeRemaining && (
          <Button size="sm" variant="primary" disabled={busy} onClick={() => void resumeRemaining(job.id)}>
            继续剩余图片
          </Button>
        )}
      </div>
    </section>
  )
}

// ===== 队列行 =====

interface QueueRowProps {
  job: JobDTO
  actions: ReactNode
  draggable?: boolean
  dragging?: boolean
  onDragStart?: () => void
  onDragOver?: (event: DragEvent) => void
  onDrop?: () => void
  onDragEnd?: () => void
}

function QueueRow({ job, actions, draggable, dragging, onDragStart, onDragOver, onDrop, onDragEnd }: QueueRowProps) {
  const excerpt = job.positive_prompt_snapshot.trim() || '（无 Prompt）'
  return (
    <li
      className={`wb-queue-item${dragging ? ' wb-queue-item--dragging' : ''}`}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
    >
      <div className="wb-queue-item__body">
        <div className="wb-queue-item__title">
          {draggable && <span className="wb-queue-item__handle" title="拖拽排序" aria-hidden="true">⋮⋮</span>}
          {job.status === 'PAUSED' && <StatusBadge status="PAUSED" />}
          <span title={excerpt}>{excerpt.length > 18 ? `${excerpt.slice(0, 18)}…` : excerpt}</span>
        </div>
        <div className="wb-queue-item__meta muted">
          {shortJobId(job.id)} · {job.requested_count} 张 ·{' '}
          {job.stages && job.stages.length > 1
            ? job.stages.map((stage) => MODULE_LABEL[stage.module_id] ?? stage.module_id).join(' + ')
            : MODULE_LABEL[job.module_id ?? ''] ?? '基础生成'}
        </div>
      </div>
      <div className="wb-queue-item__actions">{actions}</div>
    </li>
  )
}

function clampDimension(text: string): number {
  const value = Number.parseInt(text, 10)
  if (Number.isNaN(value)) return 1024
  return Math.min(4096, Math.max(64, value))
}

/**
 * 按 ParameterSpec 元数据渲染一个可配置参数（float/int/bool/enum）。
 * 值写入 WorkflowModuleRef.config——模块参数唯一事实源。
 */
function ModuleParameterField({
  param,
  value,
  onChange,
}: {
  param: ModuleParameterDTO
  value: unknown
  onChange: (value: unknown) => void
}) {
  const resolved = value ?? param.default
  const label = param.title || param.name

  if (param.type === 'bool') {
    return (
      <Field>
        <Checkbox
          checked={Boolean(resolved)}
          onChange={(event) => onChange(event.target.checked)}
          label={label}
        />
        {param.description && <p className="muted">{param.description}</p>}
      </Field>
    )
  }

  if (param.type === 'enum') {
    return (
      <Field label={label}>
        <Select
          value={String(resolved ?? '')}
          onChange={(event) => onChange(event.target.value)}
          options={(param.enum_values ?? []).map((option) => ({ value: option, label: option }))}
        />
        {param.description && <p className="muted">{param.description}</p>}
      </Field>
    )
  }

  const numeric = Number(resolved ?? 0)

  if (param.type === 'int') {
    return (
      <Field label={label}>
        <Input
          type="number"
          min={param.min ?? undefined}
          max={param.max ?? undefined}
          step={param.step ?? 1}
          value={numeric}
          onChange={(event) => onChange(Number(event.target.value))}
        />
        {param.description && <p className="muted">{param.description}</p>}
      </Field>
    )
  }

  if (param.type === 'float') {
    return (
      <Field label={label}>
        <Slider
          min={param.min ?? 0}
          max={param.max ?? 1}
          step={param.step ?? 0.01}
          value={numeric}
          onChange={(v) => onChange(v)}
          ariaLabel={label}
          valueSlot={<span>{numeric.toFixed(2)}</span>}
        />
        {param.description && <p className="muted">{param.description}</p>}
      </Field>
    )
  }

  return null
}
