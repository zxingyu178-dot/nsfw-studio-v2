// 后端 API 访问入口（前端 src/api 只封装 HTTP 调用，不做业务）。
// 开发环境经 Vite 代理 /api，无需配置地址；也可用 VITE_API_BASE_URL 显式指定。
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiRequestError extends Error {
  readonly code: string
  readonly status: number
  /** 结构化错误详情（后端 error.details；桌面 8000 当前多数不回传，有则用） */
  readonly details: unknown

  constructor(code: string, message: string, status: number, details?: unknown) {
    super(message)
    this.code = code
    this.status = status
    this.details = details
    this.name = 'ApiRequestError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    let code = `HTTP_${response.status}`
    let message = `请求失败（${response.status}）`
    let details: unknown
    try {
      const body = (await response.json()) as {
        error?: { code?: string; message?: string; details?: unknown }
      }
      if (body.error) {
        code = body.error.code ?? code
        message = body.error.message ?? message
        details = body.error.details
      }
    } catch {
      // 非 JSON 错误体，保留默认信息
    }
    throw new ApiRequestError(code, message, response.status, details)
  }
  return (await response.json()) as T
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

// ===== 类型 =====
import type {
  AssetDTO,
  AssetType,
  AssetVersionDTO,
  ComposeResult,
  EngineRuntimeDTO,
  EngineStatusDTO,
  HistoryBucket,
  HistoryResponseDTO,
  ImageDTO,
  ImageImportResponseDTO,
  ImageJobGroupDTO,
  ImagePage,
  ImageProvenanceDTO,
  ImageReferencesDTO,
  ImageReviewStatus,
  ImageSort,
  ImageStatsResponse,
  ImageVersionsDTO,
  CleanupRejectedResult,
  ThumbnailBackfillStatusDTO,
  JobDTO,
  JobEventDTO,
  ListResponse,
  ModuleCapabilitiesDTO,
  PromptDTO,
  PromptEvaluationDTO,
  PromptListParams,
  PromptMode,
  PromptStatus,
  PromptVersionDTO,
  QueueDTO,
  RecipeDTO,
  RecipeVersionDTO,
  ResumeInterruptedResult,
  ReviewStatus,
  SystemStatus,
  WorkbenchSnapshot,
} from '../types/workbench'
import type { HealthInfo } from './health'

export type { PromptListParams } from '../types/workbench'

type CommonListParams = Omit<PromptListParams, 'sort' | 'status'>

function buildQuery(params: object): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params as Record<string, unknown>)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

// ===== Prompt =====
export const promptApi = {
  list(params: PromptListParams = {}): Promise<ListResponse<PromptDTO>> {
    return request(`/api/v1/prompts${buildQuery(params)}`)
  },
  get(id: string): Promise<PromptDTO> {
    return request(`/api/v1/prompts/${id}`)
  },
  create(body: {
    name: string
    mode: PromptMode
    positive_prompt?: string
    negative_prompt?: string
    structured?: unknown
    favorite?: boolean
  }): Promise<PromptDTO> {
    return request('/api/v1/prompts', jsonInit('POST', body))
  },
  updateMeta(id: string, body: { name?: string | null; favorite?: boolean | null }): Promise<PromptDTO> {
    return request(`/api/v1/prompts/${id}`, jsonInit('PATCH', body))
  },
  addVersion(
    id: string,
    body: { mode: PromptMode; positive_prompt?: string; negative_prompt?: string; structured?: unknown },
  ): Promise<PromptVersionDTO> {
    return request(`/api/v1/prompts/${id}/versions`, jsonInit('POST', body))
  },
  listVersions(id: string): Promise<PromptVersionDTO[]> {
    return request(`/api/v1/prompts/${id}/versions`)
  },
  restoreVersion(id: string, versionId: string): Promise<PromptVersionDTO> {
    return request(`/api/v1/prompts/${id}/versions/${versionId}/restore`, jsonInit('POST', {}))
  },
  archive(id: string): Promise<PromptDTO> {
    return request(`/api/v1/prompts/${id}/archive`, jsonInit('POST', {}))
  },
  restore(id: string): Promise<PromptDTO> {
    return request(`/api/v1/prompts/${id}/restore`, jsonInit('POST', {}))
  },
  setPreviewImage(id: string, image_id: string): Promise<PromptDTO> {
    return request(`/api/v1/prompts/${id}/preview-image`, jsonInit('PUT', { image_id }))
  },
  clearPreviewImage(id: string): Promise<PromptDTO> {
    return request(`/api/v1/prompts/${id}/preview-image`, jsonInit('DELETE', {}))
  },
  compose(body: { mode: PromptMode; positive_prompt?: string; structured?: unknown }): Promise<ComposeResult> {
    return request('/api/v1/prompts/compose', jsonInit('POST', body))
  },
  /** Phase 0.17.3：人工评分（7 维 + 总分），返回最新评估记录。 */
  createEvaluation(
    id: string,
    body: {
      overall_score: number
      dimension_scores?: Record<string, number>
      notes?: string
      prompt_version_id?: string | null
    },
  ): Promise<PromptEvaluationDTO> {
    return request(`/api/v1/prompts/${id}/evaluations`, jsonInit('POST', body))
  },
  listEvaluations(id: string): Promise<PromptEvaluationDTO[]> {
    return request(`/api/v1/prompts/${id}/evaluations`)
  },
  /** Phase 0.17.3：手动设置状态（保留/候选/淘汰）。 */
  setStatus(id: string, body: { status: PromptStatus; reason?: string }): Promise<PromptDTO> {
    return request(`/api/v1/prompts/${id}/status`, jsonInit('POST', body))
  },
}

// ===== Asset =====
export interface AssetListParams extends CommonListParams {
  type?: AssetType | null
}

export const assetApi = {
  list(params: AssetListParams = {}): Promise<ListResponse<AssetDTO>> {
    return request(`/api/v1/assets${buildQuery(params)}`)
  },
  get(id: string): Promise<AssetDTO> {
    return request(`/api/v1/assets/${id}`)
  },
  create(formData: FormData): Promise<AssetDTO> {
    return request('/api/v1/assets', { method: 'POST', body: formData })
  },
  updateMeta(id: string, body: { name?: string | null; favorite?: boolean | null }): Promise<AssetDTO> {
    return request(`/api/v1/assets/${id}`, jsonInit('PATCH', body))
  },
  addVersion(id: string, formData: FormData): Promise<AssetVersionDTO> {
    return request(`/api/v1/assets/${id}/versions`, { method: 'POST', body: formData })
  },
  listVersions(id: string): Promise<AssetVersionDTO[]> {
    return request(`/api/v1/assets/${id}/versions`)
  },
  archive(id: string): Promise<AssetDTO> {
    return request(`/api/v1/assets/${id}/archive`, jsonInit('POST', {}))
  },
  restore(id: string): Promise<AssetDTO> {
    return request(`/api/v1/assets/${id}/restore`, jsonInit('POST', {}))
  },
  workbench(id: string): Promise<{ slot: AssetType; asset: AssetDTO; snapshot: WorkbenchSnapshot }> {
    return request(`/api/v1/assets/${id}/workbench`)
  },
}

// ===== Recipe =====
export const recipeApi = {
  list(params: CommonListParams = {}): Promise<ListResponse<RecipeDTO>> {
    return request(`/api/v1/recipes${buildQuery(params)}`)
  },
  get(id: string): Promise<RecipeDTO> {
    return request(`/api/v1/recipes/${id}`)
  },
  create(body: { name: string; favorite?: boolean; snapshot: WorkbenchSnapshot }): Promise<RecipeDTO> {
    return request('/api/v1/recipes', jsonInit('POST', body))
  },
  updateMeta(id: string, body: { name?: string | null; favorite?: boolean | null }): Promise<RecipeDTO> {
    return request(`/api/v1/recipes/${id}`, jsonInit('PATCH', body))
  },
  addVersion(id: string, body: { name: string; snapshot: WorkbenchSnapshot }): Promise<RecipeVersionDTO> {
    return request(`/api/v1/recipes/${id}/versions`, jsonInit('POST', body))
  },
  listVersions(id: string): Promise<RecipeVersionDTO[]> {
    return request(`/api/v1/recipes/${id}/versions`)
  },
  restoreVersion(id: string, versionId: string): Promise<RecipeVersionDTO> {
    return request(`/api/v1/recipes/${id}/versions/${versionId}/restore`, jsonInit('POST', {}))
  },
  archive(id: string): Promise<RecipeDTO> {
    return request(`/api/v1/recipes/${id}/archive`, jsonInit('POST', {}))
  },
  restore(id: string): Promise<RecipeDTO> {
    return request(`/api/v1/recipes/${id}/restore`, jsonInit('POST', {}))
  },
}

// ===== Job / Queue（Phase 2） =====
export interface JobListParams {
  status?: string | null
  limit?: number
  offset?: number
}

export const jobApi = {
  create(body: {
    snapshot: WorkbenchSnapshot
    client_request_id?: string
    queue_mode?: 'normal' | 'next'
    source?: 'web' | 'resume' | 'agent' | 'doubao'
  }): Promise<JobDTO> {
    return request('/api/v1/jobs', jsonInit('POST', body))
  },
  list(params: JobListParams = {}): Promise<ListResponse<JobDTO>> {
    return request(`/api/v1/jobs${buildQuery(params)}`)
  },
  get(id: string): Promise<JobDTO> {
    return request(`/api/v1/jobs/${id}`)
  },
  pause(id: string): Promise<JobDTO> {
    return request(`/api/v1/jobs/${id}/pause`, jsonInit('POST', {}))
  },
  resume(id: string): Promise<JobDTO> {
    return request(`/api/v1/jobs/${id}/resume`, jsonInit('POST', {}))
  },
  cancel(id: string): Promise<JobDTO> {
    return request(`/api/v1/jobs/${id}/cancel`, jsonInit('POST', {}))
  },
  resumeRemaining(id: string): Promise<JobDTO> {
    return request(`/api/v1/jobs/${id}/resume-remaining`, jsonInit('POST', {}))
  },
  resumeInterrupted(): Promise<ResumeInterruptedResult> {
    return request('/api/v1/jobs/resume-interrupted', { method: 'POST' })
  },
  queue(): Promise<QueueDTO> {
    return request('/api/v1/queue')
  },
  reorder(orderedJobIds: string[]): Promise<QueueDTO> {
    return request('/api/v1/queue/reorder', jsonInit('POST', { ordered_job_ids: orderedJobIds }))
  },
  pauseQueue(): Promise<QueueDTO> {
    return request('/api/v1/queue/pause', jsonInit('POST', {}))
  },
  resumeQueue(): Promise<QueueDTO> {
    return request('/api/v1/queue/resume', jsonInit('POST', {}))
  },
  /** v0.13.2：清理跨重启遗留的陈旧任务（QUEUED/RUNNING/PAUSED/INTERRUPTED → CANCELLED，不删图） */
  clearStale(): Promise<{ cancelled: number; job_ids: string[] }> {
    return request('/api/v1/queue/clear-stale', jsonInit('POST', {}))
  },
  engineStatus(): Promise<EngineStatusDTO> {
    return request('/api/v1/engine/status')
  },
}

// ===== 生图引擎运行时控制（Task4：启停/重启 ComfyUI 子进程） =====
export const engineRuntimeApi = {
  get(): Promise<EngineRuntimeDTO> {
    return request('/api/v1/engine/runtime')
  },
  start(): Promise<EngineRuntimeDTO> {
    return request('/api/v1/engine/runtime/start', jsonInit('POST', {}))
  },
  stop(): Promise<EngineRuntimeDTO> {
    return request('/api/v1/engine/runtime/stop', jsonInit('POST', {}))
  },
  restart(): Promise<EngineRuntimeDTO> {
    return request('/api/v1/engine/runtime/restart', jsonInit('POST', {}))
  },
}

// ===== History（Phase 4 Task5/6）：来源=jobs；按任务族两级归组 =====
export interface HistoryListParams {
  bucket?: HistoryBucket
  source?: string | null
  limit?: number
  offset?: number
}

export const historyApi = {
  list(params: HistoryListParams = {}): Promise<HistoryResponseDTO> {
    return request(`/api/v1/history${buildQuery(params)}`)
  },
}

// ===== Image / Gallery（Phase 2C；Phase 0.11 分页 + 状态 + 缩略图） =====
export interface ImageListParams {
  job_id?: string | null
  /** Phase 0.11 新审核状态筛选 */
  status?: ImageReviewStatus | null
  /** Phase 0.11 排序 */
  sort?: ImageSort | null
  /** Phase 0.11 分页（page 从 1 起） */
  page?: number
  page_size?: number
  // —— 旧参数（ImagePickerDrawer / ResultPane 仍在用，保持向后兼容） ——
  review_status?: ReviewStatus | null
  favorite?: boolean | null
  source?: string | null
  search?: string | null
  date_from?: string | null
  date_to?: string | null
  limit?: number
  offset?: number
}

export type ImageIdsParams = Omit<ImageListParams, 'page' | 'page_size' | 'limit' | 'offset'>

export interface ImageIdsResponse {
  ids: string[]
  total: number
  truncated: boolean
  limit: number
}

/** Phase 0.12 全局图库统计过滤参数（与 GET /images 同口径；不含 sort/page/limit 分页参数）。 */
export interface ImageStatsParams {
  job_id?: string | null
  review_status?: ReviewStatus | null
  favorite?: boolean | null
  source?: string | null
  kind?: string | null
  search?: string | null
  date_from?: string | null
  date_to?: string | null
  /** 新审核状态过滤：NEW/KEEP/REJECT/ARCHIVED */
  status?: ImageReviewStatus | null
}

export const imageApi = {
  /** Phase 0.11：分页图库（返回 {items,total,page,page_size,has_next}）。
   *  同时兼容旧 limit/offset/review_status（选择器 / 生成结果面板）。 */
  list(params: ImageListParams = {}): Promise<ImagePage<ImageDTO>> {
    return request(`/api/v1/images${buildQuery(params)}`)
  },
  /** 返回当前筛选命中的图片 ID，供跨页批量选择。 */
  ids(params: ImageIdsParams = {}): Promise<ImageIdsResponse> {
    return request(`/api/v1/images/ids${buildQuery(params)}`)
  },
  /** Phase 0.12：全局图库统计（与 list 同过滤口径；SQL 单行聚合）。
   *  各状态计数与收藏计数都是命中过滤后的全局数字；favorites 为独立 favorite=true 交叉计数。 */
  stats(params: ImageStatsParams = {}): Promise<ImageStatsResponse> {
    return request(`/api/v1/images/stats${buildQuery(params)}`)
  },
  get(id: string): Promise<ImageDTO> {
    return request(`/api/v1/images/${id}`)
  },
  review(id: string, reviewStatus: ReviewStatus): Promise<ImageDTO> {
    return request(`/api/v1/images/${id}/review`, jsonInit('PATCH', { review_status: reviewStatus }))
  },
  favorite(id: string, favorite: boolean): Promise<ImageDTO> {
    return request(`/api/v1/images/${id}/favorite`, jsonInit('PATCH', { favorite }))
  },
  /** Phase 0.11.1：更新单张图片审核状态（仅 NEW/KEEP/REJECT/ARCHIVED；收藏请用 favorite()） */
  setStatus(id: string, body: { status: ImageReviewStatus; note?: string }): Promise<ImageDTO> {
    return request(`/api/v1/images/${id}/status`, jsonInit('PATCH', body))
  },
  /** Phase 0.11.1：渐进预览图 URL（长边 1536 WebP）。供 <img src> / Lightbox / ReviewMode 首屏。 */
  preview(id: string): string {
    return `/api/v1/images/${id}/preview`
  },
  /** Phase 0.11：批量审核（Review Mode / 多选） */
  batchStatus(body: {
    image_ids: string[]
    status: ImageReviewStatus
    note?: string
  }): Promise<{ updated: number; items: ImageDTO[] }> {
    return request('/api/v1/images/batch-status', jsonInit('POST', body))
  },
  /** Phase 0.11：废片清理（两阶段）。confirm=false 预览候选/占用/保护数；confirm=true 真删。
   *  可带 image_ids 清理指定图（单图删除也走这里，复用引用保护）。 */
  cleanupRejected(body: { image_ids?: string[]; confirm: boolean }): Promise<CleanupRejectedResult> {
    return request('/api/v1/images/cleanup-rejected', jsonInit('POST', body))
  },
  /** Phase 0.11.1：按任务聚合分页（替代逐 Job summary 的 N+1；可翻到早期任务） */
  jobGroups(params: { page?: number; page_size?: number } = {}): Promise<ImagePage<ImageJobGroupDTO>> {
    return request(`/api/v1/images/job-groups${buildQuery(params)}`)
  },
  /** Phase 0.11.1：后台回填历史缩略图（单 worker / 低并发，不占 GPU） */
  startBackfill(body: { kind?: string; limit?: number } = {}): Promise<ThumbnailBackfillStatusDTO> {
    return request('/api/v1/images/thumbnails/backfill', jsonInit('POST', body))
  },
  backfillStatus(): Promise<ThumbnailBackfillStatusDTO> {
    return request('/api/v1/images/thumbnails/backfill/status')
  },
  stopBackfill(): Promise<ThumbnailBackfillStatusDTO> {
    return request('/api/v1/images/thumbnails/backfill/stop', jsonInit('POST', {}))
  },
  workbench(id: string): Promise<{ image_id: string; seed: number | null; snapshot: WorkbenchSnapshot }> {
    return request(`/api/v1/images/${id}/workbench`)
  },
  jobSummary(jobId: string): Promise<{
    job_id: string
    total: number
    unreviewed: number
    kept: number
    rejected: number
    favorites: number
  }> {
    return request(`/api/v1/images/by-job/${jobId}/summary`)
  },
  /** 图库高清放大（§二十/§二十四）：创建 process Job，由同一队列 Worker 执行 */
  upscale(imageIds: string[]): Promise<JobDTO> {
    return request('/api/v1/images/upscale', jsonInit('POST', { image_ids: imageIds }))
  },
  /** 父子关系（§十九）：派生版本 / 来源原图 */
  versions(id: string): Promise<ImageVersionsDTO> {
    return request(`/api/v1/images/${id}/versions`)
  },
  /** Image Provenance（Task10）：来源任务 / Stage / 模块 / 双指纹 / Seed */
  provenance(id: string): Promise<ImageProvenanceDTO> {
    return request(`/api/v1/images/${id}/provenance`)
  },
  /** 外部图片批量导入（Phase 5 §三/§六/§二十三）：sha256 去重、部分失败继续 */
  importFiles(files: File[]): Promise<ImageImportResponseDTO> {
    const formData = new FormData()
    for (const file of files) formData.append('files', file)
    return request('/api/v1/images/import', { method: 'POST', body: formData })
  },
  /** 图片引用保护检查（Phase 5 §十一） */
  references(id: string): Promise<ImageReferencesDTO> {
    return request(`/api/v1/images/${id}/references`)
  },
}

// ===== WorkflowModule 能力（Phase 5 §二十：图片生成 Gate 判定） =====
export const moduleApi = {
  list(): Promise<ModuleCapabilitiesDTO[]> {
    return request('/api/v1/modules')
  },
}

// ===== 任务事件 SSE（§二十三：SSE 只通知；数据库状态才是唯一事实源） =====
export function subscribeJobEvents(
  onEvent: (event: JobEventDTO) => void,
  onConnection?: (state: 'open' | 'error') => void,
): () => void {
  const source = new EventSource(`${API_BASE}/api/v1/events/jobs`)
  source.onopen = () => onConnection?.('open')
  source.onerror = () => onConnection?.('error')
  source.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data as string) as JobEventDTO)
    } catch {
      // 忽略无法解析的事件（keepalive 等）
    }
  }
  return () => source.close()
}

// ===== 系统状态摘要（Phase 0.12 Task7：Settings 系统维护中心只读数据） =====
/** POST /system/request-shutdown 返回（202 Accepted；loopback only） */
export interface RequestShutdownResult {
  accepted: boolean
  already_pending?: boolean
  helper?: string
  helper_launched?: boolean
  message?: string
}

export const systemApi = {
  status(): Promise<SystemStatus> {
    return request('/api/v1/system/status')
  },
  /** Phase 0.14 Task6：应用内"停止全部后台"自停桥。
   *  仅回环可用；后端回 202 {accepted:true} 后，由一次性 detached helper 经官方
   *  lifecycle CLI 停止整套（当前生成 / Mobile Review / Studio Backend / 受管 ComfyUI）。
   *  前端绝不直接杀进程；这里只发请求并展示"正在停止…"反馈。 */
  requestShutdown(): Promise<RequestShutdownResult> {
    return request('/api/v1/system/request-shutdown', jsonInit('POST', {}))
  },
}

// ===== Mobile Review Bridge（Phase 0.13：局域网手机审核桥，独立 8767） =====
/** Bridge 受管运行时状态机（与后端 MobileReviewRuntimeService 对齐） */
export type MobileReviewRuntimeState =
  | 'STOPPED'
  | 'STARTING'
  | 'RUNNING'
  | 'STOPPING'
  | 'PORT_CONFLICT'
  | 'ERROR'

export interface MobileReviewRuntimeDTO {
  state: MobileReviewRuntimeState
  host: string
  port: number
  owned: boolean
  pid: number | null
  parent_pid: number | null
  started_at: string | null
  detail: string
  log_location: string | null
  health: Record<string, unknown>
}

/** POST /mobile-review/pairing/code 返回：6 位一次性码 + 有效期秒数（后端固定 600s） */
export interface MobilePairingCodeDTO {
  code: string
  expires_in_seconds: number
}

/** 已配对设备（桌面管理视图；token 绝不下发） */
export interface PairedDeviceDTO {
  device_id: string
  installation_id: string
  name: string
  paired_at: string
  last_seen_at?: string | null
  revoked?: boolean
}

/**
 * 手机审核桥桌面管理 API（全部走 8000 loopback，复用 EngineRuntime 同款启停语义，不写第二套 runtime）。
 * 注意：设备列表 / 撤销设备依赖 /mobile-review/devices 管理端点；后端未就绪时本组件优雅降级为提示。
 */
export const mobileReviewApi = {
  runtime(): Promise<MobileReviewRuntimeDTO> {
    return request('/api/v1/mobile-review/runtime')
  },
  start(): Promise<MobileReviewRuntimeDTO> {
    return request('/api/v1/mobile-review/runtime/start', jsonInit('POST', {}))
  },
  stop(): Promise<MobileReviewRuntimeDTO> {
    return request('/api/v1/mobile-review/runtime/stop', jsonInit('POST', {}))
  },
  restart(): Promise<MobileReviewRuntimeDTO> {
    return request('/api/v1/mobile-review/runtime/restart', jsonInit('POST', {}))
  },
  /** 生成 6 位一次性配对码（明文只返回这一次；10 分钟有效） */
  createPairingCode(): Promise<MobilePairingCodeDTO> {
    return request('/api/v1/mobile-review/pairing/code', jsonInit('POST', {}))
  },
  /** 已配对设备列表（桌面 loopback 管理端点） */
  devices(): Promise<PairedDeviceDTO[]> {
    return request('/api/v1/mobile-review/devices')
  },
  /** 吊销设备 token（此后该手机 Bearer 立即失效） */
  revokeDevice(deviceId: string): Promise<unknown> {
    return request(`/api/v1/mobile-review/devices/${deviceId}/revoke`, jsonInit('POST', {}))
  },
}

// ===== 冻结式审核会话（Phase 0.13：桌面 / 手机共用 ImageReviewSessionService） =====
/** SessionSummary（/review/* 无 envelope，直出） */
export interface ReviewSessionSummaryDTO {
  id: string
  status: 'ACTIVE' | 'COMPLETED' | string
  total_count: number
  seen_count: number
  current_index: number
  created_at: string
  updated_at: string
  filter: Record<string, unknown>
  /** v0.37：ACTIVE 为 null；COMPLETED / ABANDONED / EMPTY */
  ended_reason?: 'COMPLETED' | 'ABANDONED' | 'EMPTY' | null
}

/** MobileImageSummary DTO：字段与手机端一致（image_id / is_favorite，不是 id / favorite） */
export interface ReviewQueueImageDTO {
  image_id: string
  width: number
  height: number
  created_at: string
  updated_at: string
  status: ImageReviewStatus
  is_favorite: boolean
  kind: string
  job_id: string | null
  seed: number | null
  thumbnail_url?: string
  preview_url?: string
  original_url?: string
}

export interface ReviewQueueItemDTO {
  /** 冻结的绝对队列下标（不随打标压缩） */
  index: number
  seen: boolean
  image: ReviewQueueImageDTO
}

export interface ReviewQueuePageDTO {
  items: ReviewQueueItemDTO[]
  total: number
  page: number
  page_size: number
}

export interface ReviewDecisionResultDTO {
  session: ReviewSessionSummaryDTO
  item_index: number
  image: ReviewQueueImageDTO
}

export interface ReviewSessionCompleteDTO extends ReviewSessionSummaryDTO {
  completed: boolean
  remaining_count: number
}

export interface ReviewSessionAbandonDTO extends ReviewSessionSummaryDTO {
  abandoned: boolean
  remaining_count: number
}

export interface ReviewNewCountDTO {
  session_id: string
  count: number
  filter: Record<string, unknown>
}

export interface CreateReviewSessionBody {
  filter?: Record<string, unknown> | null
  /** all=全部未审核（默认）；only_new=仅新到（排除旧会话成员） */
  mode?: 'all' | 'only_new'
  exclude_session_id?: string | null
  /** 显式换批时把旧 ACTIVE 会话标为 ABANDONED */
  close_active?: boolean
}

export const reviewSessionApi = {
  /** 创建冻结审核会话（filter 默认 status=NEW, created_desc） */
  createSession(
    filter?: Record<string, unknown>,
    options: Omit<CreateReviewSessionBody, 'filter'> = {},
  ): Promise<ReviewSessionSummaryDTO> {
    const body: CreateReviewSessionBody = { filter: filter ?? null, ...options }
    return request('/api/v1/review/sessions', jsonInit('POST', body))
  },
  /** 恢复最近会话（不重建；无会话 404 REVIEW_SESSION_NOT_FOUND） */
  latestSession(): Promise<ReviewSessionSummaryDTO> {
    return request('/api/v1/review/sessions/latest')
  },
  queuePage(sessionId: string, page: number, pageSize = 50): Promise<ReviewQueuePageDTO> {
    return request(`/api/v1/review/sessions/${sessionId}/queue${buildQuery({ page, page_size: pageSize })}`)
  },
  /** 一次 decision（同事务）：action=KEEP/REJECT/RESET；favorite 独立；乐观锁冲突 409 REVIEW_CONFLICT */
  decide(
    sessionId: string,
    body: {
      item_index: number
      action?: 'KEEP' | 'REJECT' | 'RESET'
      favorite?: boolean
      expected_status?: string
      expected_updated_at?: string
    },
  ): Promise<ReviewDecisionResultDTO> {
    return request(`/api/v1/review/sessions/${sessionId}/decision`, jsonInit('POST', body))
  },
  /** 记录浏览位置（断点续看） */
  reportPosition(sessionId: string, itemIndex: number): Promise<ReviewSessionSummaryDTO> {
    return request(`/api/v1/review/sessions/${sessionId}/position`, jsonInit('POST', { item_index: itemIndex }))
  },
  /** 标记完成（仍有未审则返回 remaining_count，不强完成） */
  complete(sessionId: string): Promise<ReviewSessionCompleteDTO> {
    return request(`/api/v1/review/sessions/${sessionId}/complete`, jsonInit('POST', {}))
  },
  /** 显式放弃会话（保留 items，不删除数据） */
  abandon(sessionId: string): Promise<ReviewSessionAbandonDTO> {
    return request(`/api/v1/review/sessions/${sessionId}/abandon`, jsonInit('POST', {}))
  },
  /** 当前会话之外的待审核图片数量（真实 DB 查询，排除会话成员） */
  newCount(sessionId: string): Promise<ReviewNewCountDTO> {
    return request(`/api/v1/review/sessions/${sessionId}/new-count`)
  },
}

// ===== 健康检查 =====
export function getHealth(): Promise<HealthInfo> {
  return request<HealthInfo>('/api/v1/health')
}
