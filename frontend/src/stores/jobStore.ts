// 任务 / 队列 / 引擎状态仓库（Phase 2 规范 §二十三、§五十-§五十四）。
// 原则：SSE 只负责"实时通知"，数据库 Job 状态才是唯一事实源；
// 任何事件（含 SSE 重连）都回源 GET /jobs、/queue、/engine/status。
import { useSyncExternalStore } from 'react'
import { ApiRequestError, jobApi, subscribeJobEvents } from '../api/client'
import type { EngineStatusDTO, JobDTO, QueueDTO, WorkbenchSnapshot } from '../types/workbench'

export interface JobStoreState {
  engine: EngineStatusDTO | null
  engineLoaded: boolean
  queue: QueueDTO | null
  /** 本页提交/关注的 Job（含 items，用于中栏进度与缩略图） */
  trackedJob: JobDTO | null
  submitting: boolean
  /** 正在执行队列操作的 Job id */
  busyJobId: string | null
  sseConnected: boolean
  lastError: string | null
}

let state: JobStoreState = {
  engine: null,
  engineLoaded: false,
  queue: null,
  trackedJob: null,
  submitting: false,
  busyJobId: null,
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

// ===== 数据刷新（唯一事实源 = 数据库） =====

let refreshTimer: number | null = null
let refreshing = false

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
  } catch (error) {
    setState({
      lastError: error instanceof ApiRequestError ? error.message : '无法获取任务状态',
      engineLoaded: true,
    })
  } finally {
    refreshing = false
  }
}

/** 打开本页时关注某个 Job（如刷新后从"当前任务"点选） */
export function trackJob(jobId: string): void {
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

async function runJobAction(jobId: string, action: () => Promise<JobDTO>): Promise<JobDTO | null> {
  setState({ busyJobId: jobId, lastError: null })
  try {
    const job = await action()
    setState({ busyJobId: null })
    void refreshJobs()
    return job
  } catch (error) {
    setState({
      busyJobId: null,
      lastError: error instanceof ApiRequestError ? error.message : '操作失败',
    })
    return null
  }
}

export function pauseJob(jobId: string): Promise<JobDTO | null> {
  return runJobAction(jobId, () => jobApi.pause(jobId))
}

export function resumeJob(jobId: string): Promise<JobDTO | null> {
  return runJobAction(jobId, () => jobApi.resume(jobId))
}

export function cancelJob(jobId: string): Promise<JobDTO | null> {
  return runJobAction(jobId, () => jobApi.cancel(jobId))
}

/** 继续剩余图片：创建子 Job（§二十），并把界面关注点切到子 Job */
export async function resumeRemaining(jobId: string): Promise<JobDTO | null> {
  const job = await runJobAction(jobId, () => jobApi.resumeRemaining(jobId))
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

export async function resumeQueue(): Promise<void> {
  try {
    await jobApi.resumeQueue()
    void refreshJobs()
  } catch (error) {
    setState({ lastError: error instanceof ApiRequestError ? error.message : '恢复队列失败' })
  }
}

// ===== App 生命周期（SSE + 兜底轮询） =====

let started = false
let pollTimer: number | null = null
let unsubscribeSse: (() => void) | null = null

/** 由 MainLayout 调用一次；SSE 断线时兜底轮询仍保证状态最终一致。 */
export function startJobStore(): void {
  if (started) return
  started = true
  void refreshJobs()
  unsubscribeSse = subscribeJobEvents(
    () => scheduleJobRefresh(),
    (connection) => setState({ sseConnected: connection === 'open' }),
  )
  pollTimer = window.setInterval(() => {
    void refreshJobs()
  }, 10000)
}

export function stopJobStore(): void {
  if (pollTimer !== null) window.clearInterval(pollTimer)
  pollTimer = null
  unsubscribeSse?.()
  unsubscribeSse = null
  started = false
}