// 后端 API 访问入口（前端 src/api 只封装 HTTP 调用，不做业务）。
// 开发环境经 Vite 代理 /api，无需配置地址；也可用 VITE_API_BASE_URL 显式指定。
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiRequestError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: string, message: string, status: number) {
    super(message)
    this.code = code
    this.status = status
    this.name = 'ApiRequestError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    let code = `HTTP_${response.status}`
    let message = `请求失败（${response.status}）`
    try {
      const body = (await response.json()) as { error?: { code?: string; message?: string } }
      if (body.error) {
        code = body.error.code ?? code
        message = body.error.message ?? message
      }
    } catch {
      // 非 JSON 错误体，保留默认信息
    }
    throw new ApiRequestError(code, message, response.status)
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
  EngineStatusDTO,
  HistoryBucket,
  HistoryResponseDTO,
  ImageDTO,
  ImageProvenanceDTO,
  ImageVersionsDTO,
  JobDTO,
  JobEventDTO,
  ListResponse,
  PromptDTO,
  PromptMode,
  PromptVersionDTO,
  QueueDTO,
  RecipeDTO,
  RecipeVersionDTO,
  ReviewStatus,
  WorkbenchSnapshot,
} from '../types/workbench'
import type { HealthInfo } from './health'

export interface PromptListParams {
  search?: string
  favorite?: boolean | null
  archived?: boolean | null
  limit?: number
  offset?: number
}

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
  compose(body: { mode: PromptMode; positive_prompt?: string; structured?: unknown }): Promise<ComposeResult> {
    return request('/api/v1/prompts/compose', jsonInit('POST', body))
  },
}

// ===== Asset =====
export interface AssetListParams extends PromptListParams {
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
  list(params: PromptListParams = {}): Promise<ListResponse<RecipeDTO>> {
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
  queue(): Promise<QueueDTO> {
    return request('/api/v1/queue')
  },
  reorder(orderedJobIds: string[]): Promise<QueueDTO> {
    return request('/api/v1/queue/reorder', jsonInit('POST', { ordered_job_ids: orderedJobIds }))
  },
  resumeQueue(): Promise<{ queue_paused: boolean }> {
    return request('/api/v1/queue/resume', jsonInit('POST', {}))
  },
  engineStatus(): Promise<EngineStatusDTO> {
    return request('/api/v1/engine/status')
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

// ===== Image / Gallery（Phase 2C） =====
export interface ImageListParams {
  job_id?: string | null
  review_status?: ReviewStatus | null
  favorite?: boolean | null
  source?: string | null
  date_from?: string | null
  date_to?: string | null
  limit?: number
  offset?: number
}

export const imageApi = {
  list(params: ImageListParams = {}): Promise<ListResponse<ImageDTO>> {
    return request(`/api/v1/images${buildQuery(params)}`)
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

// ===== 健康检查 =====
export function getHealth(): Promise<HealthInfo> {
  return request<HealthInfo>('/api/v1/health')
}
