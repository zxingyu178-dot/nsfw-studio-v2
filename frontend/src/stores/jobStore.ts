// 任务 / 队列 / 引擎状态仓库（Phase 2 规范 §二十三、§五十-§五十四）。
// 原则：SSE 只负责"实时通知"，数据库 Job 状态才是唯一事实源；
// 任何事件（含 SSE 重连）都回源 GET /jobs、/queue、/engine/status。
import { useSyncExternalStore } from 'react'
import { ApiRequestError, jobApi, subscribeJobEvents } from '../api/client'
import type { EngineStatusDTO, JobDTO, JobEventDTO, QueueDTO, WorkbenchSnapshot } from '../types/workbench'

/**
 * v0.15 Task 8：实时采样进度（瞬态，不入持久 JobDTO）。
 * 由 ITEM_PROGRESS SSE 直接驱动，页面刷新/重连后随下一次回源重建。
 */
export interface LiveProgress {
  /** 归一化进度 0~1（引擎不支持时为 null） */
  progress?: number | null
  /** 引擎阶段标识（sampling / save_image / upscale …） */
  engineStage?: string | null
  /** 当前 Stage 序号（从 0 开始） */
  stageIndex?: number | null
  /** 采样当前步数（仅采样型工作流有值） */
  step?: number | null
  /** 采样总步数（仅采样型工作流有值） */
  maxStep?: number | null
  updatedAt: number
  /** v0.15.1：所属 StageItem id（多阶段身份，唯一索引键）；同一 job_item_id 在 basic/upscale 各有一条 */
  stageItemId?: string
  /** 内部：所属 Job id，用于 Job 终态/切换时清理 */
  jobId?: string
}

export interface JobStoreState {
  engine: EngineStatusDTO | null
  engineLoaded: boolean
  queue: QueueDTO | null
  /** 本页提交/关注的 Job（含 items，用于中栏进度与缩略图） */
  trackedJob: JobDTO | null
  /**
   * v0.15.1：按 stage_item_id 索引的实时进度（瞬态，不随持久快照刷新）。
   * 必须用 stage_item_id 而非 job_item_id：同一逻辑槽位在 basic/upscale 两个 Stage
   * 共用同一 job_item_id，按 job_item_id 会让 stage0 的进度覆盖/误删 stage1 的进度。
   */
  liveProgressByStageItem: Record<string, LiveProgress>
  submitting: boolean
  /** 正在执行队列操作的 Job id */
  busyJobId: string | null
  /** v0.15.1：busyJobId 对应的具体动作（pause/resume/cancel），用于按钮显示“正在暂停/继续/取消…” */
  busyJobAction: 'pause' | 'resume' | 'cancel' | null
  sseConnected: boolean
  lastError: string | null
}

let state: JobStoreState = {
  engine: null,
  engineLoaded: false,
  queue: null,
  trackedJob: null,
  liveProgressByStageItem: {},
  submitting: false,
  busyJobId: null,
  busyJobAction: null,
  sseConnected: false,
  lastError: null,
}

const listeners = new Set<() => void>()

function setState(patch: Partial<JobStoreState>): void {
  state = { ...state, ...patch }
  listeners.forEach((listener) => listener())
}

function subscribeJobStore(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getJobStoreState(): JobStoreState {
  return state
}

export function useJobStore(): JobStoreState {
  return useSyncExternalStore(subscribeJobStore, getJobStoreState)
}

const TERMINAL = new Set(['COMPLETED', 'FAILED', 'CANCELLED', 'INTERRUPTED'])

/** 界面展示的任务：优先本页关注的 Job，否则当前执行中的 Job（刷新后仍能看到进度）。 */
export function activeJob(store: JobStoreState): JobDTO | null {
  return store.trackedJob ?? store.queue?.running ?? null
}

// ===== 实时进度（v0.15 Task 8：瞬态层，不塞进持久 JobDTO） =====

const ITEM_TERMINAL_EVENTS = new Set(['ITEM_COMPLETED', 'ITEM_FAILED', 'ITEM_CANCELLED'])
const JOB_TERMINAL_EVENTS = new Set(['JOB_COMPLETED', 'JOB_FAILED', 'JOB_CANCELLED'])

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function str(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null
}

/** ITEM_PROGRESS 的唯一键：优先 stage_item_id（多阶段）；缺失时回退信封 item_id（兼容旧后端）。 */
function liveProgressKey(itemId: string | null | undefined, payload: Record<string, unknown>): string | null {
  return str(payload.stage_item_id) ?? itemId ?? null
}

function setLiveProgress(itemId: string | null | undefined, jobId: string, payload: Record<string, unknown>): void {
  const key = liveProgressKey(itemId, payload)
  if (!key) return
  const next = { ...state.liveProgressByStageItem }
  next[key] = {
    progress: num(payload.progress),
    engineStage: typeof payload.stage === 'string' ? payload.stage : null,
    stageIndex: num(payload.stage_index),
    step: num(payload.step),
    maxStep: num(payload.max_step),
    updatedAt: Date.now(),
    stageItemId: str(payload.stage_item_id) ?? undefined,
    jobId,
  }
  setState({ liveProgressByStageItem: next })
}

function clearLiveProgressStageItem(stageItemId: string | null | undefined): void {
  if (!stageItemId || !state.liveProgressByStageItem[stageItemId]) return
  const next = { ...state.liveProgressByStageItem }
  delete next[stageItemId]
  setState({ liveProgressByStageItem: next })
}

function clearLiveProgressForJob(jobId: string): void {
  const current = state.liveProgressByStageItem
  const kept = Object.fromEntries(
    Object.entries(current).filter(([, v]) => v.jobId !== jobId),
  )
  if (Object.keys(kept).length !== Object.keys(current).length) {
    setState({ liveProgressByStageItem: kept })
  }
}

function clearAllLiveProgress(): void {
  if (Object.keys(state.liveProgressByStageItem).length === 0) return
  setState({ liveProgressByStageItem: {} })
}

/**
 * SSE 事件分流（v0.15 Task 8）：
 * - ITEM_PROGRESS 只更新瞬态 liveProgress，**不触发** GET /queue、/engine/status、/job；
 * - 关键 lifecycle 事件（创建/开始/完成/失败/暂停/取消/阶段切换…）才回源刷新；
 * - 终态事件清理对应瞬态进度。
 */
export function handleJobEvent(event: JobEventDTO): void {
  if (event.type === 'ITEM_PROGRESS') {
    setLiveProgress(event.item_id, event.job_id, event.payload ?? {})
    return
  }
  if (ITEM_TERMINAL_EVENTS.has(event.type)) {
    // v0.15.1：优先按 stage_item_id 精确清理；旧后端无该字段时回退信封 item_id。
    const payloadStageItemId = str(event.payload?.stage_item_id)
    if (payloadStageItemId) {
      clearLiveProgressStageItem(payloadStageItemId)
    } else if (event.item_id) {
      clearLiveProgressStageItem(event.item_id)
    }
  }
  if (JOB_TERMINAL_EVENTS.has(event.type)) {
    clearLiveProgressForJob(event.job_id)
  }
  // 关键 lifecycle 事件才回源（progress 事件已在上面直接 return）
  scheduleJobRefresh()
}

/**
 * 回源后根据持久 DTO 收敛瞬态进度（v0.15.1：按 stage_item_id 判定）。
 * 仅当“该 stage_item_id 对应的 StageItem 自身已终态”时才删除其 live 进度——
 * 同一 job_item_id 的 stage0 已完成、stage1 仍在跑时，绝不误删 stage1 的进度。
 */
function pruneLiveProgress(jobs: JobDTO[]): void {
  const terminalStageItemIds = new Set<string>()
  for (const job of jobs) {
    for (const stage of job.stages ?? []) {
      for (const item of stage.items ?? []) {
        if (['COMPLETED', 'FAILED', 'CANCELLED'].includes(item.status)) {
          terminalStageItemIds.add(item.id)
        }
      }
    }
  }
  const before = Object.keys(state.liveProgressByStageItem).length
  if (!before) return
  const kept = Object.fromEntries(
    Object.entries(state.liveProgressByStageItem).filter(([id]) => !terminalStageItemIds.has(id)),
  )
  if (Object.keys(kept).length !== before) setState({ liveProgressByStageItem: kept })
}

// ===== 数据刷新（唯一事实源 = 数据库） =====

let refreshTimer: number | null = null
let refreshing = false
let lastSnapshotAt = 0

export function scheduleJobRefresh(delayMs = 300): void {
  if (refreshTimer !== null) window.clearTimeout(refreshTimer)
  refreshTimer = window.setTimeout(() => {
    refreshTimer = null
    void refreshJobs()
  }, delayMs)
}

export async function refreshJobs(): Promise<void> {
  if (refreshing) return
  refreshing = true
  try {
    const [queue, engine] = await Promise.all([jobApi.queue(), jobApi.engineStatus()])
    let tracked = state.trackedJob
    if (tracked && !TERMINAL.has(tracked.status)) {
      const trackedId = tracked.id
      const inQueue =
        (queue.running?.id === trackedId && queue.running) ||
        queue.queued.find((job) => job.id === trackedId) ||
        queue.paused.find((job) => job.id === trackedId) ||
        null
      tracked = inQueue ?? (await jobApi.get(trackedId))
    }
    setState({ queue, engine, engineLoaded: true, trackedJob: tracked })
    lastSnapshotAt = Date.now()
    // 瞬态进度收敛：持久 DTO 已终态的 item 不再保留 live
    pruneLiveProgress([queue.running, ...queue.queued, ...queue.paused, tracked].filter(
      (j): j is JobDTO => j !== null && j !== undefined,
    ))
  } catch (error) {
    setState({
      lastError: error instanceof ApiRequestError ? error.message : '无法获取任务状态',
      engineLoaded: true,
    })
  } finally {
    refreshing = false
  }
}

/** 打开本页时关注某个 Job（如刷新后从"当前任务"点选）；切换关注时清理瞬态进度。 */
export function trackJob(jobId: string): void {
  clearAllLiveProgress()
  void jobApi
    .get(jobId)
    .then((job) => setState({ trackedJob: job }))
    .catch((error: unknown) =>
      setState({ lastError: error instanceof ApiRequestError ? error.message : '无法获取任务' }),
    )
}

// ===== 提交（§五十三：前端只走 POST /jobs，绝不直连 ComfyUI） =====

// 相同快照的失败重试复用同一 client_request_id（§十二 幂等）
let pendingRequest: { id: string; snapshotJson: string } | null = null

function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `req-${Date.now()}-${Math.floor(Math.random() * 1e9)}`
}

export async function submitGeneration(
  snapshot: WorkbenchSnapshot,
  queueMode: 'normal' | 'next',
): Promise<JobDTO | null> {
  if (state.submitting) return null
  setState({ submitting: true, lastError: null })
  const snapshotJson = JSON.stringify(snapshot)
  if (!pendingRequest || pendingRequest.snapshotJson !== snapshotJson) {
    pendingRequest = { id: uuid(), snapshotJson }
  }
  try {
    const job = await jobApi.create({
      snapshot,
      client_request_id: pendingRequest.id,
      queue_mode: queueMode,
      source: 'web',
    })
    pendingRequest = null
    clearAllLiveProgress()
    setState({ trackedJob: job, submitting: false })
    void refreshJobs()
    return job
  } catch (error) {
    setState({
      submitting: false,
      lastError: error instanceof ApiRequestError ? error.message : '任务提交失败',
    })
    return null
  }
}

// ===== 状态操作（暂停 / 继续 / 取消 / 续跑剩余 / 队列） =====

type JobActionKind = 'pause' | 'resume' | 'cancel'

async function runJobAction(
  jobId: string,
  kind: JobActionKind,
  action: () => Promise<JobDTO>,
): Promise<JobDTO | null> {
  setState({ busyJobId: jobId, busyJobAction: kind, lastError: null })
  try {
    const job = await action()
    setState({ busyJobId: null, busyJobAction: null })
    void refreshJobs()
    return job
  } catch (error) {
    setState({
      busyJobId: null,
      busyJobAction: null,
      lastError: error instanceof ApiRequestError ? error.message : '操作失败',
    })
    return null
  }
}

export function pauseJob(jobId: string): Promise<JobDTO | null> {
  return runJobAction(jobId, 'pause', () => jobApi.pause(jobId))
}

export function resumeJob(jobId: string): Promise<JobDTO | null> {
  return runJobAction(jobId, 'resume', () => jobApi.resume(jobId))
}

export function cancelJob(jobId: string): Promise<JobDTO | null> {
  return runJobAction(jobId, 'cancel', () => jobApi.cancel(jobId))
}

/** 继续剩余图片：创建子 Job（§二十），并把界面关注点切到子 Job */
export async function resumeRemaining(jobId: string): Promise<JobDTO | null> {
  const job = await runJobAction(jobId, 'resume', () => jobApi.resumeRemaining(jobId))
  if (job) setState({ trackedJob: job })
  return job
}

export async function reorderQueue(orderedJobIds: string[]): Promise<void> {
  try {
    const queue = await jobApi.reorder(orderedJobIds)
    setState({ queue })
  } catch (error) {
    setState({ lastError: error instanceof ApiRequestError ? error.message : '排序失败' })
    void refreshJobs()
  }
}

export async function pauseQueue(): Promise<void> {
  try {
    await jobApi.pauseQueue()
    void refreshJobs()
  } catch (error) {
    setState({ lastError: error instanceof ApiRequestError ? error.message : '暂停队列失败' })
  }
}

export async function resumeQueue(): Promise<void> {
  try {
    await jobApi.resumeQueue()
    void refreshJobs()
  } catch (error) {
    setState({ lastError: error instanceof ApiRequestError ? error.message : '恢复队列失败' })
  }
}

/** v0.13.2：清理陈旧任务（跨重启遗留的 QUEUED/RUNNING/PAUSED/INTERRUPTED → CANCELLED，不删图）。
 *  返回实际清理数量；失败时写入 lastError 并返回 0。 */
export async function clearStaleJobs(): Promise<number> {
  setState({ lastError: null })
  try {
    const res = await jobApi.clearStale()
    await refreshJobs()
    return res.cancelled
  } catch (error) {
    setState({ lastError: error instanceof ApiRequestError ? error.message : '清理陈旧任务失败' })
    return 0
  }
}

// ===== App 生命周期（SSE + 兜底轮询） =====

let started = false
let pollTimer: number | null = null
let unsubscribeSse: (() => void) | null = null

function onJobVisibilityChange(): void {
  if (document.visibilityState === 'visible') void refreshJobs()
}

/** 由 MainLayout 调用一次；SSE 断线时兜底轮询仍保证状态最终一致。 */
export function startJobStore(): void {
  if (started) return
  started = true
  setState({ sseConnected: false })
  void refreshJobs()
  unsubscribeSse = subscribeJobEvents(
    (event) => handleJobEvent(event),
    (connection) => setState({ sseConnected: connection === 'open' }),
  )
  document.addEventListener('visibilitychange', onJobVisibilityChange)
  pollTimer = window.setInterval(() => {
    if (document.visibilityState === 'hidden') return
    const age = Date.now() - lastSnapshotAt
    if (state.sseConnected && age >= 0 && age < 60000) return
    void refreshJobs()
  }, 10000)
}

export function stopJobStore(): void {
  document.removeEventListener('visibilitychange', onJobVisibilityChange)
  if (pollTimer !== null) window.clearInterval(pollTimer)
  pollTimer = null
  unsubscribeSse?.()
  unsubscribeSse = null
  started = false
}

/**
 * 读取某 StageItem（stage_item_id）的实时进度；无则 undefined。
 * 注意：必须传 StageItem.id（多阶段唯一），不要传 job_item_id。
 */
export function liveProgressForStageItem(
  store: JobStoreState,
  stageItemId: string | null | undefined,
): LiveProgress | undefined {
  return stageItemId ? store.liveProgressByStageItem[stageItemId] : undefined
}

/** 测试隔离：重置仓库内存态与定时器（仅测试使用）。 */
export function __resetJobStoreForTest(): void {
  document.removeEventListener('visibilitychange', onJobVisibilityChange)
  lastSnapshotAt = 0
  if (refreshTimer !== null) window.clearTimeout(refreshTimer)
  refreshTimer = null
  if (pollTimer !== null) window.clearInterval(pollTimer)
  pollTimer = null
  unsubscribeSse?.()
  unsubscribeSse = null
  started = false
  refreshing = false
  state = {
    engine: null,
    engineLoaded: false,
    queue: null,
    trackedJob: null,
    liveProgressByStageItem: {},
    submitting: false,
    busyJobId: null,
    busyJobAction: null,
    sseConnected: false,
    lastError: null,
  }
  listeners.clear()
}