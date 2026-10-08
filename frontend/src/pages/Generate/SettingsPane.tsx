import { useState, type DragEvent, type ReactNode } from 'react'
import {
  hasUpscaleModule,
  setCount,
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
  JOB_STATUS_LABEL,
  MODULE_LABEL,
  STAGE_LABEL,
  shortJobId,
  type JobDTO,
} from '../../types/workbench'
import { overallProgress, stageProgressLines } from '../../utils/jobProgress'

/** 右栏（规范 §五十一、§五十三、§五十四）：真实 Engine 状态 / 参数 / 生成按钮 / 当前任务 / 队列。
 *
 * Phase 5 §二十：图片生成模式需要可用 Module（Gate）；不可用时明确提示并禁用提交。
 */
export function SettingsPane({ imageGenAvailable }: { imageGenAvailable: boolean }) {
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
  // Task8：开关是派生值；真实状态是 workflowModules 列表（含完整执行身份）
  const upscaleEnabled = hasUpscaleModule(state.workflowModules)
  // Phase 5：图片生成模式的提交前置条件（Gate / 输入图片 / 丢失标记）
  const inputImage = state.inputImages[0] ?? null
  const imageGateBlocked = state.mode === 'image' && !imageGenAvailable
  const generateHint = store.submitting
    ? undefined
    : engineOffline
      ? 'Engine 离线，无法提交'
      : !hasPrompt
        ? '请先填写 Prompt'
        : imageGateBlocked
          ? '图片生成：尚未配置可用工作流'
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

  return (
    <div className="pane">
      <header className="pane__header">
        <h2 className="pane__title">生成配置</h2>
      </header>

      {/* ===== 真实 Engine 状态 ===== */}
      <div className="field">
        <span className="field__label">引擎</span>
        <p className="field__static">
          <span
            className={`engine-status engine-status--${
              store.engineLoaded ? (store.engine?.online ? 'online' : 'offline') : 'checking'
            }`}
            title={store.engine?.detail}
          >
            <span className="engine-status__dot" aria-hidden="true" />
            {store.engine?.online
              ? `${store.engine.engine_name} ${store.engine.engine_version}`
              : store.engineLoaded
                ? '离线'
                : '检测中'}
          </span>
        </p>
      </div>

      {/* ===== 工作流（§十五：轻量模块区，不做节点编辑器） ===== */}
      <div className="field">
        <span className="field__label">工作流</span>
        <div className="workflow-modules">
          <p className="field__static">① 基础生成</p>
          <label className="field__check">
            <input
              type="checkbox"
              checked={upscaleEnabled}
              onChange={(event) => setUpscaleEnabled(event.target.checked)}
            />
            ② 高清放大
          </label>
          {upscaleEnabled && (
            <p className="muted">原图全部完成后，依次生成高清图（原图与高清保持父子关系）。</p>
          )}
        </div>
      </div>

      <div className="field">
        <label className="field__label" htmlFor="size-width">宽度 (px)</label>
        <input
          id="size-width"
          className="input"
          type="number"
          min={64}
          max={4096}
          step={64}
          value={widthText}
          onChange={(event) => setWidthText(event.target.value)}
          onBlur={commitSize}
        />
      </div>
      <div className="field">
        <label className="field__label" htmlFor="size-height">高度 (px)</label>
        <input
          id="size-height"
          className="input"
          type="number"
          min={64}
          max={4096}
          step={64}
          value={heightText}
          onChange={(event) => setHeightText(event.target.value)}
          onBlur={commitSize}
        />
      </div>

      <div className="field">
        <label className="field__label" htmlFor="gen-count">数量</label>
        <select
          id="gen-count"
          className="input"
          value={state.count}
          onChange={(event) => setCount(Number(event.target.value))}
        >
          {[1, 2, 4, 6, 8].map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </div>

      <div className="field">
        <div className="field__label-row">
          <span className="field__label">Seed</span>
          {state.seedMode === 'fixed' && (
            <button type="button" className="btn btn--ghost btn--xs" onClick={() => setSeed(null)}>
              恢复随机
            </button>
          )}
        </div>
        {state.seedMode === 'fixed' && state.seed !== null ? (
          <p className="field__static">
            固定 {state.seed}
            <span className="muted">（单张精确复现；选择数量 &gt; 1 将自动切回随机）</span>
          </p>
        ) : (
          <p className="field__static">随机（每张独立）</p>
        )}
      </div>

      {/* ===== 生成按钮（§五十三：只提交 Job，不直连引擎） ===== */}
      {imageGateBlocked && (
        <p className="notice notice--warn">
          图片生成：尚未配置可用工作流（等待模型方案确认）。可先选择输入图片并保存配方。
        </p>
      )}
      <div className="generate-actions">
        <button
          type="button"
          className="btn btn--primary btn--lg generate-actions__main"
          disabled={store.submitting || generateHint !== undefined}
          title={generateHint}
          onClick={() => void handleGenerate('normal')}
        >
          {store.submitting ? '提交中…' : '生成'}
        </button>
        <button
          type="button"
          className="btn btn--sm"
          disabled={store.submitting || generateHint !== undefined}
          title={generateHint}
          onClick={() => void handleGenerate('next')}
        >
          优先生成（插队）
        </button>
      </div>
      {store.lastError && <p className="notice notice--error" role="alert">{store.lastError}</p>}
      {notice && <p className="notice notice--ok" role="status">{notice}</p>}

      {/* ===== 当前任务（§五十一） ===== */}
      {job && <CurrentJobCard job={job} busy={store.busyJobId === job.id} />}

      {/* ===== 队列（§五十四） ===== */}
      <section className="queue">
        <h3 className="queue__title">队列</h3>
        {store.queue?.worker.queue_paused && (
          <div className="notice notice--warn" role="alert">
            <p style={{ margin: '0 0 6px' }}>
              队列已自动暂停：{store.queue.worker.queue_paused_reason ?? '系统性失败'}
            </p>
            <button type="button" className="btn btn--sm" onClick={() => void resumeQueue()}>
              恢复队列
            </button>
          </div>
        )}
        {queued.length === 0 && paused.length === 0 && <p className="muted">暂无等待任务</p>}
        <ul className="queue-list">
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
                    <button type="button" className="btn btn--ghost btn--xs" onClick={() => moveToFront(item.id)}>
                      优先
                    </button>
                  )}
                  <button type="button" className="btn btn--ghost btn--xs" onClick={() => void pauseJob(item.id)}>
                    暂停
                  </button>
                  <button type="button" className="btn btn--ghost btn--xs" onClick={() => void cancelJob(item.id)}>
                    取消
                  </button>
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
                  <button type="button" className="btn btn--ghost btn--xs" onClick={() => void resumeJob(item.id)}>
                    继续
                  </button>
                  <button type="button" className="btn btn--ghost btn--xs" onClick={() => void cancelJob(item.id)}>
                    取消
                  </button>
                </>
              }
            />
          ))}
        </ul>
      </section>
    </div>
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
    <section className="job-card">
      <div className="job-card__head">
        <span className={`status-chip status-chip--${job.status.toLowerCase()}`}>
          {JOB_STATUS_LABEL[job.status]}
        </span>
        <span className="muted">{shortJobId(job.id)}</span>
      </div>
      <p className="job-card__title" title={excerpt}>
        {excerpt.length > 28 ? `${excerpt.slice(0, 28)}…` : excerpt}
      </p>
      <div className="progress-bar" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
        <span className="progress-bar__fill" style={{ width: `${Math.min(100, Math.max(0, progress))}%` }} />
      </div>
      {stageLines.length > 0 ? (
        <ul className="stage-progress" aria-label="分阶段进度">
          {stageLines.map((line) => (
            <li key={line.key} className={line.done ? 'stage-progress__done' : undefined}>
              {line.text}
            </li>
          ))}
        </ul>
      ) : (
        <p className="job-card__meta">
          {progressText}
          {runningItem?.current_stage ? ` · ${STAGE_LABEL[runningItem.current_stage] ?? runningItem.current_stage}` : ''}
        </p>
      )}
      <p className="job-card__meta">{moduleLabel}</p>
      {job.resume_of_job_id && (
        <p className="muted">续跑自 {shortJobId(job.resume_of_job_id)}</p>
      )}
      {job.error_message && <p className="notice notice--error">{job.error_type}：{job.error_message}</p>}

      <div className="job-card__actions">
        {job.status === 'RUNNING' && !job.pause_requested && (
          <button type="button" className="btn btn--sm" disabled={busy} onClick={() => void pauseJob(job.id)}>
            暂停
          </button>
        )}
        {job.status === 'RUNNING' && job.pause_requested && (
          <span className="muted">将在当前图完成后暂停…</span>
        )}
        {job.status === 'QUEUED' && (
          <button type="button" className="btn btn--sm" disabled={busy} onClick={() => void pauseJob(job.id)}>
            暂停
          </button>
        )}
        {job.status === 'PAUSED' && (
          <button type="button" className="btn btn--sm" disabled={busy} onClick={() => void resumeJob(job.id)}>
            继续
          </button>
        )}
        {job.status === 'RUNNING' && job.cancel_requested && (
          <span className="muted">正在取消…</span>
        )}
        {['QUEUED', 'RUNNING', 'PAUSED'].includes(job.status) && !job.cancel_requested && (
          <button type="button" className="btn btn--ghost btn--sm" disabled={busy} onClick={() => void cancelJob(job.id)}>
            取消
          </button>
        )}
        {canResumeRemaining && (
          <button type="button" className="btn btn--primary btn--sm" disabled={busy} onClick={() => void resumeRemaining(job.id)}>
            继续剩余图片
          </button>
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
      className={`queue-item${dragging ? ' queue-item--dragging' : ''}`}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
    >
      <div className="queue-item__body">
        <div className="queue-item__title">
          {draggable && <span className="queue-item__handle" title="拖拽排序" aria-hidden="true">⋮⋮</span>}
          {job.status === 'PAUSED' && <span className="status-chip status-chip--paused">已暂停</span>}
          <span title={excerpt}>{excerpt.length > 18 ? `${excerpt.slice(0, 18)}…` : excerpt}</span>
        </div>
        <div className="queue-item__meta muted">
          {shortJobId(job.id)} · {job.requested_count} 张 ·{' '}
          {job.stages && job.stages.length > 1
            ? job.stages.map((stage) => MODULE_LABEL[stage.module_id] ?? stage.module_id).join(' + ')
            : MODULE_LABEL[job.module_id ?? ''] ?? '基础生成'}
        </div>
      </div>
      <div className="queue-item__actions">{actions}</div>
    </li>
  )
}

function clampDimension(text: string): number {
  const value = Number.parseInt(text, 10)
  if (Number.isNaN(value)) return 1024
  return Math.min(4096, Math.max(64, value))
}