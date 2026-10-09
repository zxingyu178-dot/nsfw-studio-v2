// 前后端共享契约类型（与 backend/app/schemas 双侧镜像，字段名不得另起）
export type PromptMode = 'structured' | 'full'
export type AssetType = 'face' | 'clothing' | 'pose' | 'scene'
/** Phase 6 Task7：生成模式（文生图 / 图片生成）——显式字段，禁止靠 input_images 反推 */
export type GenerationMode = 'text' | 'image'

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
  /** Phase 6 Task7：Recipe / Job 往返携带生成模式（旧数据无该字段 → null，前端按输入图推断） */
  generation_mode?: GenerationMode | null
  params: Record<string, unknown>
}

export interface WorkflowSnapshotDTO {
  modules: WorkflowModuleRef[]
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
  /** Phase 5 §九：输入图快照（含 missing 丢失标记） */
  input_images: RecipeInputImageDTO[]
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

/** 工作流模块执行身份（Phase 4 Task8/9；Phase 5.1 Task1 正式类型化）。
 *
 * - 普通新建工作台只携带 module_id（+ 可选 config），提交时由后端解析当前默认版本；
 * - 从历史 Job / Image / 配方恢复时携带**完整身份**（含双指纹），提交时固定原版本精确重现；
 * - config：模块参数唯一入口（如 img2img 的 denoise），经 Recipe → Job → JobStage.config_json 单链。
 */
export interface WorkflowModuleRef {
  module_id: string
  module_version?: string
  provider?: string
  binding_version?: string
  workflow_hash?: string | null
  binding_hash?: string | null
  config?: Record<string, unknown>
}

/** 工作台输入图片（Phase 5 §八：统一 image_id，max=1，role=source）。
 *
 * missing 仅用于"配方恢复后图片已丢失"的显式标记（不进入提交体，后端模型忽略未知字段）。
 */
export interface InputImageRef {
  role: 'source'
  image_id: string
  missing?: boolean
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
  workflow_modules: WorkflowModuleRef[]
  input_images?: InputImageRef[]
  /**
   * Phase 6 Task7：生成模式显式保存与恢复。
   * 向后兼容：null / undefined = 旧快照，按 input_images / Primary Module 推断。
   */
  generation_mode?: GenerationMode | null
  source_prompt_id?: string | null
  source_prompt_version_id?: string | null
}

/** RecipeVersion 输入图快照（Phase 5 §九：image_id + file hash + role；缺失必须显式提示） */
export interface RecipeInputImageDTO {
  role: string
  image_id: string
  sha256: string | null
  missing: boolean
}

/** WorkflowModule 能力声明 + 真实可用性（Phase 5 §十四/§二十；Phase 5.1 Task7）。
 *
 * Gate 判定唯一依据 = ``available``（registered ≠ available：
 * 未配置 provider binding 的模块 registered=true 但 available=false）。
 */
export interface ModuleCapabilitiesDTO {
  module_id: string
  module_version: string
  title: string
  description: string
  uses_seed: boolean
  input_kind: string
  input_required: boolean
  input_role: string
  output_kind: string
  parent_policy: string
  output_cardinality: number
  registered: boolean
  available: boolean
  provider: string | null
  binding_version: string | null
  unavailable_reason: string | null
}

/** 外部图片导入结果（Phase 5 §二十三：成功 / 已存在 / 失败 三类明细） */
export interface ImageImportResponseDTO {
  imported: { filename: string; image: ImageDTO }[]
  duplicates: { filename: string; image_id: string; sha256: string }[]
  failed: { filename: string; error_code: string; message: string }[]
  imported_count: number
  duplicate_count: number
  failed_count: number
}

/** 图片引用保护检查（Phase 5 §十一） */
export interface ImageReferencesDTO {
  image_id: string
  total: number
  active_job_ids: string[]
  references: Record<string, string[]>
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

export interface JobStageItemDTO {
  id: string
  job_stage_id: string
  job_item_id: string
  item_index: number
  input_image_id: string | null
  output_image_id: string | null
  /** Phase 4 Task3：本 StageItem 实际使用的 Seed（uses_seed=false 的 Stage 为 null） */
  seed: number | null
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | 'INTERRUPTED'
  engine_job_id: string | null
  progress: number | null
  error_type: string | null
  error_message: string | null
  retry_count: number
  started_at: string | null
  finished_at: string | null
}

/** Stage（Phase 3 §二十四）：module/status/total/completed/current_item/progress */
export interface JobStageDTO {
  id: string
  stage_index: number
  module_id: string
  module_version: string
  provider: string | null
  binding_version: string | null
  workflow_hash: string | null
  binding_hash: string | null
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | 'INTERRUPTED'
  total_count: number
  completed_count: number
  current_item: number | null
  progress: number | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  items: JobStageItemDTO[]
}

export interface JobDTO {
  id: string
  source: string
  client_request_id: string | null
  status: JobStatus
  job_kind: 'generate' | 'process'
  prompt_mode: PromptMode
  positive_prompt_snapshot: string
  negative_prompt_snapshot: string
  structured_prompt: StructuredPrompt
  workbench_snapshot: WorkbenchSnapshot
  generation_settings: Record<string, unknown>
  workflow_snapshot: WorkflowSnapshotDTO
  module_id: string | null
  module_version: string | null
  provider: string | null
  binding_version: string | null
  workflow_hash: string | null
  binding_hash: string | null
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
  stages: JobStageDTO[]
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

export interface ImageVersionsDTO {
  image: ImageDTO
  parent: ImageDTO | null
  children: ImageDTO[]
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

// ===== Phase 4：History（Task5/6） =====

export type HistoryBucket = 'all' | 'active' | 'completed' | 'failed' | 'cancelled'

/** 历史任务族：原任务 + 其续跑任务（两级归组，Task6） */
export interface HistoryEntryDTO {
  root_job_id: string
  root: JobDTO
  resumes: JobDTO[]
}

export interface HistoryResponseDTO {
  items: HistoryEntryDTO[]
  total: number
  limit: number
  offset: number
}

// ===== Phase 4：Image Provenance（Task10） =====

export interface ImageProvenanceDTO {
  image_id: string
  kind: string
  parent_image_id: string | null
  root_image_id: string
  scale: number | null
  job_id: string | null
  job_item_id: string | null
  stage_id: string | null
  stage_index: number | null
  stage_item_id: string | null
  module_id: string | null
  module_version: string | null
  provider: string | null
  binding_version: string | null
  workflow_hash: string | null
  binding_hash: string | null
  seed: number | null
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
  img2img: '图生图',
  upscale: '高清放大',
}

export const JOB_SOURCE_LABEL: Record<string, string> = {
  web: 'Web',
  resume: '续跑',
  agent: 'Agent',
  doubao: 'Doubao',
}

export const HISTORY_BUCKET_LABEL: Record<HistoryBucket, string> = {
  all: '全部',
  active: '进行中',
  completed: '完成',
  failed: '失败',
  cancelled: '取消',
}

export const IMAGE_KIND_LABEL: Record<string, string> = {
  original: '原图',
  upscaled: '高清',
  processed: '处理图',
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
