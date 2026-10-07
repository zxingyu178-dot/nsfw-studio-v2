// 后端 API 访问入口（前端 src/api 只封装 HTTP 调用，不做业务）。
// 开发环境经 Vite 代理 /api，无需配置地址；也可用 VITE_API_BASE_URL 显式指定。
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export interface HealthInfo {
  status: string
  version: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    throw new Error(`API ${path} 请求失败: HTTP ${response.status}`)
  }
  return (await response.json()) as T
}

export function getHealth(): Promise<HealthInfo> {
  return request<HealthInfo>('/api/v1/health')
}
