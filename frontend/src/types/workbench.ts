// 前后端共享契约类型（与 backend/app/schemas 双侧镜像，字段名不得另起）
export type PromptMode = 'structured' | 'full'
export type AssetType = 'face' | 'clothing' | 'pose' | 'scene'

/** 结构化 Prompt 八部分（顺序永久固定，规范 §八） */
export interface StructuredPrompt {
  style: string
  face: string
  clothing: string
  pose: string
  scene: string
  composition: string
  lighting: string
  extra: string
}

export const STRUCTURED_FIELDS: { key: keyof StructuredPrompt; label: string }[] = [
  { key: 'style', label: '风格' },
  { key: 'face', label: '人脸' },
  { key: 'clothing', label: '服饰' },
  { key: 'pose', label: '动作' },
  { key: 'scene', label: '场景' },
  { key: 'composition', label: '镜头/构图' },
  { key: 'lighting', label: '光线' },
  { key: 'extra', label: '额外描述' },
]

export const ASSET_TYPES: { key: AssetType; label: string }[] = [
  { key: 'face', label: '人脸' },
  { key: 'clothing', label: '服饰' },
  { key: 'pose', label: '动作' },
  { key: 'scene', label: '场景' },
]

export const ASSET_TYPE_LABEL: Record<AssetType, string> = {
  face: '人脸',
  clothing: '服饰',
  pose: '动作',
  scene: '场景',
}

export function emptyStructured(): StructuredPrompt {
  return { style: '', face: '', clothing: '', pose: '', scene: '', composition: '', lighting: '', extra: '' }
}

// ===== DTO（与后端响应模型镜像） =====
export interface PromptVersionDTO {
  id: string
  prompt_id: string
  version_no: number
  mode: PromptMode
  positive_prompt: string
  negative_prompt: string
  structured: StructuredPrompt
  created_at: string
}

export interface PromptDTO {
  id: string
  name: string
  favorite: boolean
  archived: boolean
  created_at: string
  updated_at: string
  current_version: PromptVersionDTO | null
}

export interface AssetVersionDTO {
  id: string
  asset_id: string
  version_no: number
  prompt_text: string
  notes: string
  preview_path: string | null
  reference_images: string[]
  tags: string[]
  created_at: string
}

export interface AssetDTO {
  id: string
  type: AssetType
  name: string
  favorite: boolean
  archived: boolean
  source_image_id: string | null
  created_at: string
  updated_at: string
  current_version: AssetVersionDTO | null
}

export interface SelectedAssetRef {
  asset_id: string
  asset_version_id: string
  name: string
}

export interface GenerationSettingsDTO {
  model_ref: string | null
  width: number
  height: number
  seed_mode: string
  params: Record<string, unknown>
}

export interface WorkflowSnapshotDTO {
  modules: Record<string, unknown>[]
}

export interface RecipeAssetSnapshotDTO {
  id: string
  slot: AssetType
  asset_id: string
  asset_version_id: string
  asset_name: string
  prompt: string
  preview_path: string | null
}

export interface RecipeVersionDTO {
  id: string
  recipe_id: string
  version_no: number
  prompt_mode: PromptMode
  positive_prompt_snapshot: string
  negative_prompt_snapshot: string
  structured_prompt: StructuredPrompt
  source_prompt_id: string | null
  source_prompt_version_id: string | null
  generation_settings: GenerationSettingsDTO
  workflow_snapshot: WorkflowSnapshotDTO
  default_count: number
  created_at: string
  asset_snapshots: RecipeAssetSnapshotDTO[]
}

export interface RecipeDTO {
  id: string
  name: string
  favorite: boolean
  archived: boolean
  created_at: string
  updated_at: string
  current_version: RecipeVersionDTO | null
}

/** 统一工作台快照（规范 §五十二）：Prompt / Asset / Recipe（未来 Image / Agent）共用 */
export interface WorkbenchSnapshot {
  prompt_mode: PromptMode
  structured_prompt: StructuredPrompt
  full_prompt: string
  negative_prompt: string
  selected_assets: Partial<Record<AssetType, SelectedAssetRef>>
  width: number
  height: number
  count: number
  seed_mode: string
  seed?: number | null
  workflow_modules: Record<string, unknown>[]
  source_prompt_id?: string | null
  source_prompt_version_id?: string | null
}

export interface ListResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

/** prompt_text 合成预览（后端权威规则） */
export interface ComposeResult {
  composed_prompt: string
}

export function assetPreviewUrl(assetId: string, version?: number): string {
  return `/api/v1/assets/${assetId}/preview${version ? `?version=${version}` : ''}`
}

export function imageContentUrl(imageId: string): string {
  return `/api/v1/images/${imageId}/content`
}

// ===== Phase 2：Job / Queue / Image =====
export type JobStatus =
  | 'QUEUED' | 'RUNNING' | 'PAUSED' | 'INTERRUPTED' | 'COMPLETED' | 'FAILED' | 'CANCELLED'
export type ReviewStatus = 'UNREVIEWED' | 'KEPT' | 'REJECTED'

export interface JobItemDTO {
  id: string
  job_id: string
  item_index: number
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | 'INTERRUPTED'
  seed: number | null
  engine_job_id: string | null
  current_stage: string | null
  progress: number | null
  image_id: string | null
  error_type: string | null
  error_message: string | null
  retry_count: number
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface JobDTO {
  id: string
  source: string
  client_request_id: string | null
  status: JobStatus
  prompt_mode: PromptMode
  positive_prompt_snapshot: string
  negative_prompt_snapshot: string
  structured_prompt: StructuredPrompt
  workbench_snapshot: WorkbenchSnapshot
  generation_settings: Record<string, unknown>
  workflow_snapshot: Record<string, unknown>
  module_id: string | null
  module_version: string | null
  provider: string | null
  binding_version: string | null
  workflow_hash: string | null
  requested_count: number
  completed_count: number
  queue_position: number | null
  priority: number
  resume_of_job_id: string | null
  pause_requested: boolean
  cancel_requested: boolean
  error_type: string | null
  error_message: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  updated_at: string
  items: JobItemDTO[]
  idempotent_replay?: boolean | null
  disk_space?: string | null
}

export interface QueueDTO {
  worker: { running: boolean; queue_paused?: boolean; queue_paused_reason?: string | null; current_job_id?: string | null; adapter?: string }
  running: JobDTO | null
  queued: JobDTO[]
  paused: JobDTO[]
}

export interface ImageDTO {
  id: string
  job_id: string | null
  job_item_id: string | null
  parent_image_id: string | null
  kind: string
  file_path: string
  width: number
  height: number
  seed: number | null
  review_status: ReviewStatus
  favorite: boolean
  source: string
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface EngineStatusDTO {
  online: boolean
  detail: string
  engine_name: string
  engine_version: string
}

export interface JobEventDTO {
  type: string
  job_id: string
  item_id?: string | null
  payload?: Record<string, unknown>
  time: string
}

// ===== Phase 2 展示标签 =====
export const JOB_STATUS_LABEL: Record<JobStatus, string> = {
  QUEUED: '排队中',
  RUNNING: '生成中',
  PAUSED: '已暂停',
  INTERRUPTED: '已中断',
  COMPLETED: '已完成',
  FAILED: '失败',
  CANCELLED: '已取消',
}

export const JOB_ITEM_STATUS_LABEL: Record<JobItemDTO['status'], string> = {
  QUEUED: '排队中',
  RUNNING: '生成中',
  COMPLETED: '完成',
  FAILED: '失败',
  CANCELLED: '已取消',
  INTERRUPTED: '已中断',
}

export const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  UNREVIEWED: '未审核',
  KEPT: '保留',
  REJECTED: '淘汰',
}

export const IMAGE_SOURCE_LABEL: Record<string, string> = {
  comfyui: '本机 ComfyUI',
  mock: '测试引擎',
  import: '导入',
}

export const MODULE_LABEL: Record<string, string> = {
  basic_generate: '基础生成',
}

export const STAGE_LABEL: Record<string, string> = {
  submit: '提交',
  queued: '排队',
  execution: '执行',
  sampling: '采样',
  save_image: '保存',
  done: '完成',
  error: '错误',
}

/** job_<uuid> → JOB-<短 ID>（规范 §四十九） */
export function shortJobId(id: string): string {
  return `JOB-${id.replace(/^job_/, '').slice(0, 8)}`
}
