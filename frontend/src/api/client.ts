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
  ListResponse,
  PromptDTO,
  PromptMode,
  PromptVersionDTO,
  RecipeDTO,
  RecipeVersionDTO,
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

// ===== 健康检查 =====
export function getHealth(): Promise<HealthInfo> {
  return request<HealthInfo>('/api/v1/health')
}
