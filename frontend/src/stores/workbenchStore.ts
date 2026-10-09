// 生成工作台统一状态（Phase 1 规范 §五十一、§五十二）。
// Prompt / Asset / Recipe（未来 Image / Agent）→ 生成工作台 都通过 WorkbenchSnapshot
// 注入本仓库，禁止把工作台状态散落在各组件。
import { useSyncExternalStore } from 'react'
import {
  emptyStructured,
  type AssetType,
  type InputImageRef,
  type ModuleCapabilitiesDTO,
  type PromptMode,
  type SelectedAssetRef,
  type StructuredPrompt,
  type WorkbenchSnapshot,
  type WorkflowModuleRef,
} from '../types/workbench'

/** 生成模式（Phase 5 §二十）：文生图 / 图片生成（图片生成需要输入图片 + 可用 Module） */
export type WorkbenchMode = 'text' | 'image'

export interface WorkbenchState {
  promptMode: PromptMode
  structured: StructuredPrompt
  fullPrompt: string
  negativePrompt: string
  selectedAssets: Partial<Record<AssetType, SelectedAssetRef>>
  /** 生成模式：text=文生图；image=图片生成（输入图片 + Prompt → 处理型 Module） */
  mode: WorkbenchMode
  /** 输入图片（§八：max=1，role=source；missing=true 表示配方恢复后图片已丢失） */
  inputImages: InputImageRef[]
  width: number
  height: number
  count: number
  seedMode: 'random' | 'fixed'
  seed: number | null
  /**
   * 工作流模块列表（Phase 4 Task8）：真实状态是模块列表，不是 upscaleEnabled 布尔。
   * Phase 5.1 Task6：Primary Module 与生成模式必须一致——
   * 文生图 = basic_generate；图片生成 = 可用的图片条件模块（如 img2img）；
   * 普通新建：只携带 module_id；历史恢复（Task9）：携带完整执行身份。
   */
  workflowModules: WorkflowModuleRef[]
  /** /modules 能力目录（Phase 5.1 Task7）：Gate 判定唯一依据（available=true） */
  moduleCatalog: ModuleCapabilitiesDTO[]
  sourcePromptId: string | null
  sourcePromptVersionId: string | null
  sourceRecipeId: string | null
}

function initialState(): WorkbenchState {
  return {
    promptMode: 'structured',
    structured: emptyStructured(),
    fullPrompt: '',
    negativePrompt: '',
    selectedAssets: {},
    mode: 'text',
    inputImages: [],
    width: 1024,
    height: 1024,
    count: 1,
    seedMode: 'random',
    seed: null,
    workflowModules: [{ module_id: 'basic_generate' }],
    moduleCatalog: [],
    sourcePromptId: null,
    sourcePromptVersionId: null,
    sourceRecipeId: null,
  }
}

let state: WorkbenchState = initialState()
const listeners = new Set<() => void>()

function setState(patch: Partial<WorkbenchState>): void {
  state = { ...state, ...patch }
  listeners.forEach((listener) => listener())
}

export function subscribeWorkbench(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getWorkbenchState(): WorkbenchState {
  return state
}

export function useWorkbench(): WorkbenchState {
  return useSyncExternalStore(subscribeWorkbench, getWorkbenchState)
}

/** 派生值：高清放大是否开启（Task8：供 UI/进度展示，不再作为唯一状态） */
export function hasUpscaleModule(modules: WorkflowModuleRef[]): boolean {
  return modules.some((module) => module.module_id === 'upscale')
}

/** Task7：可用的图片条件模块（input_required=true + output_kind=processed + available=true） */
export function availableImageModuleIds(catalog: ModuleCapabilitiesDTO[]): string[] {
  return catalog
    .filter((module) => module.available && module.input_required && module.output_kind === 'processed')
    .map((module) => module.module_id)
}

/** Task6：primary module 是否消费输入图（图片生成模式提交前置条件） */
export function isImageCapablePrimary(state: WorkbenchState): boolean {
  const primary = state.workflowModules[0]?.module_id
  return primary !== undefined && availableImageModuleIds(state.moduleCatalog).includes(primary)
}

/**
 * Task6/Task2：按模式保证 Primary Module 一致性（禁止自相矛盾状态）。
 *
 * - 文生图：primary 必须是 basic_generate（保留完整身份；换模块时丢弃旧身份）；
 * - 图片生成：primary 必须是**可用**的图片条件模块；恢复出的完整身份在可用时原样保留，
 *   不可用 / 是 basic_generate（历史矛盾数据）时切换到目录中的可用模块（丢弃旧身份）；
 * - 非 Primary 模块（高清 / 未来 Reference 后处理…）**保持原有顺序与完整身份**：
 *   禁止重建裸 {module_id:'upscale'}，从 History / Recipe / Image 恢复出的
 *   module_version / provider / binding_version / 双 hash / config 必须原样保留；
 * - 切换模式不影响输入图片（回到图片模式不丢选择）。
 */
function normalizeModules(
  modules: WorkflowModuleRef[],
  mode: WorkbenchMode,
  catalog: ModuleCapabilitiesDTO[],
): WorkflowModuleRef[] {
  const [primary = null, ...rest] = modules
  const imageModules = availableImageModuleIds(catalog)
  let nextPrimary: WorkflowModuleRef
  if (mode === 'text') {
    nextPrimary = primary?.module_id === 'basic_generate' ? primary : { module_id: 'basic_generate' }
  } else if (primary && imageModules.includes(primary.module_id)) {
    nextPrimary = primary // 完整身份（含双指纹）在模块可用时原样保留
  } else if (imageModules.length > 0) {
    nextPrimary = { module_id: imageModules[0] }
  } else {
    // 目录尚未加载或没有可用图片模块：保留现状（由 Gate 阻止提交，绝不静默降级）
    nextPrimary = primary ?? { module_id: 'basic_generate' }
  }
  return [nextPrimary, ...rest].map((module) => ({
    ...module,
    config: { ...(module.config ?? {}) },
  }))
}

/** 当前状态 → 统一快照（保存 Prompt / 保存配方 / 提交 Job 时使用；模块身份与 config 原样保留，Task9/Task3/Task7） */
export function snapshotFromState(): WorkbenchSnapshot {
  return {
    prompt_mode: state.promptMode,
    structured_prompt: { ...state.structured },
    full_prompt: state.promptMode === 'full' ? state.fullPrompt : '',
    negative_prompt: state.negativePrompt,
    selected_assets: { ...state.selectedAssets },
    // Task7：生成模式显式进入快照（不靠 input_images 反推；Reference 等未来模式不会丢）
    generation_mode: state.mode,
    // §八/§十：输入图片只在"图片生成"模式下进入快照（文生图语义不携带输入图）
    input_images:
      state.mode === 'image'
        ? state.inputImages.map(({ role, image_id }) => ({ role, image_id }))
        : [],
    width: state.width,
    height: state.height,
    count: state.count,
    seed_mode: state.seedMode,
    seed: state.seedMode === 'fixed' ? state.seed : null,
    workflow_modules: state.workflowModules.map((module) => ({
      ...module,
      config: { ...(module.config ?? {}) },
    })),
    source_prompt_id: state.sourcePromptId,
    source_prompt_version_id: state.sourcePromptVersionId,
  }
}

/** 整体注入快照（Prompt / Recipe / Image / History → 工作台，100% 恢复，含模块身份 §十六/Task9/Task7） */
export function hydrateWorkbench(snapshot: WorkbenchSnapshot, sourceRecipeId: string | null = null): void {
  const modules = (snapshot.workflow_modules ?? []) as WorkflowModuleRef[]
  const inputImages = (snapshot.input_images ?? []).map((ref) => ({ ...ref }))
  // Task7：显式 generation_mode 优先；旧快照（无该字段）才按输入图推断（向后兼容）
  const mode: WorkbenchMode =
    snapshot.generation_mode ?? (inputImages.length > 0 ? 'image' : 'text')
  setState({
    promptMode: snapshot.prompt_mode,
    structured: { ...emptyStructured(), ...snapshot.structured_prompt },
    fullPrompt: snapshot.full_prompt,
    negativePrompt: snapshot.negative_prompt,
    selectedAssets: { ...snapshot.selected_assets },
    // 带输入图恢复（配方 / 图库"用作输入图片"）→ 自动进入图片生成模式
    mode,
    inputImages,
    width: snapshot.width,
    height: snapshot.height,
    count: snapshot.count,
    // Seed 默认 random；仅"使用此图 Seed"等显式固定时才恢复固定值（规范 §四十七）
    seedMode: typeof snapshot.seed === 'number' ? 'fixed' : 'random',
    seed: typeof snapshot.seed === 'number' ? snapshot.seed : null,
    workflowModules: normalizeModules(modules, mode, state.moduleCatalog),
    sourcePromptId: snapshot.source_prompt_id ?? null,
    sourcePromptVersionId: snapshot.source_prompt_version_id ?? null,
    sourceRecipeId,
  })
}

/** 清空工作台（新建） */
export function resetWorkbench(): void {
  state = { ...initialState(), moduleCatalog: state.moduleCatalog }
  listeners.forEach((listener) => listener())
}

/** 空工作台快照（Phase 5.1：外部导入图 → 图生图，Prompt 为空的第一版语义） */
export function emptyWorkbenchSnapshot(): WorkbenchSnapshot {
  const initial = initialState()
  return {
    prompt_mode: initial.promptMode,
    structured_prompt: { ...initial.structured },
    full_prompt: '',
    negative_prompt: '',
    selected_assets: {},
    // Task7：空工作台 = 文生图（显式模式；"用作输入图 / 图生图"入口会显式覆盖为 image）
    generation_mode: 'text',
    input_images: [],
    width: initial.width,
    height: initial.height,
    count: initial.count,
    seed_mode: initial.seedMode,
    seed: null,
    // 由 hydrate → normalize 按图片生成模式校正为可用图片模块（Task6）
    workflow_modules: [{ module_id: 'basic_generate' }],
    source_prompt_id: null,
    source_prompt_version_id: null,
  }
}

// ===== 细粒度操作 =====
export function setPromptMode(mode: PromptMode): void {
  setState({ promptMode: mode })
}

export function setStructuredField(field: keyof StructuredPrompt, value: string): void {
  setState({ structured: { ...state.structured, [field]: value } })
}

export function setFullPrompt(value: string): void {
  setState({ fullPrompt: value })
}

export function setNegativePrompt(value: string): void {
  setState({ negativePrompt: value })
}

export function setSize(width: number, height: number): void {
  setState({ width, height })
}

export function setCount(count: number): void {
  // §0.4：固定 Seed 仅用于单张精确复现；用户把数量改成 >1 → 自动切回随机 Seed
  if (count > 1 && state.seedMode === 'fixed') {
    setState({ count, seedMode: 'random', seed: null })
    return
  }
  setState({ count })
}

/** 固定 Seed（"使用此图 Seed"）或恢复随机（seed = null） */
export function setSeed(seed: number | null): void {
  // §0.4：固定 Seed 自动收敛为单张（count = 1）
  if (seed !== null) {
    setState({ seedMode: 'fixed', seed, count: 1 })
    return
  }
  setState({ seedMode: 'random', seed: null })
}

/** 工作流开关（§十五/Task8）：② 高清放大 —— 增删列表中的 upscale 模块（保留其余模块身份） */
export function setUpscaleEnabled(enabled: boolean): void {
  const base = state.workflowModules.filter((module) => module.module_id !== 'upscale')
  const kept = base.length > 0 ? base : [{ module_id: 'basic_generate' } as WorkflowModuleRef]
  setState({
    workflowModules: (enabled ? [...kept, { module_id: 'upscale' }] : kept).map((module) => ({ ...module })),
  })
}

/** 生成模式切换（§二十 + Phase 5.1 Task6）：Primary Module 同步切换，禁止模式与模块自相矛盾 */
export function setWorkbenchMode(mode: WorkbenchMode): void {
  setState({
    mode,
    workflowModules: normalizeModules(state.workflowModules, mode, state.moduleCatalog),
  })
}

/** /modules 能力目录注入（Task7：Gate 判定唯一依据 available=true；同时校正 Primary Module） */
export function setModuleCatalog(catalog: ModuleCapabilitiesDTO[]): void {
  setState({
    moduleCatalog: catalog,
    // Task6：目录到达后重新校正（历史矛盾数据 → 可用图片模块）
    workflowModules: normalizeModules(state.workflowModules, state.mode, catalog),
  })
}

/** 设置 Primary Module 的 config（Task3：模块参数唯一入口，如 img2img 的 denoise） */
export function setPrimaryModuleConfig(patch: Record<string, unknown>): void {
  const [primary, ...rest] = state.workflowModules
  if (!primary) return
  setState({
    workflowModules: [{ ...primary, config: { ...(primary.config ?? {}), ...patch } }, ...rest],
  })
}

/** 设置输入图片（§七：max=1，选择新图即替换；来源必须是 Gallery image_id） */
export function setInputImage(imageId: string): void {
  setState({
    inputImages: [{ role: 'source', image_id: imageId }],
    mode: 'image',
    // 切到图片生成 → Primary Module 同步为可用图片模块（Task6）
    workflowModules: normalizeModules(state.workflowModules, 'image', state.moduleCatalog),
  })
}

/** 移除输入图片 */
export function clearInputImage(): void {
  setState({ inputImages: [] })
}

/**
 * 选择素材到 slot（规范 §四十五、§四十六）：
 * 素材 Prompt 填入对应结构化字段（在前），用户之后可手工追加；同时记录素材版本引用，
 * 保存配方时固化为快照。编辑该字段不会回写素材（原 AssetVersion 不受影响）。
 */
export function applyAssetToSlot(slot: AssetType, promptText: string, ref: SelectedAssetRef): void {
  setState({
    structured: { ...state.structured, [slot]: promptText },
    selectedAssets: { ...state.selectedAssets, [slot]: ref },
  })
}

export function clearAssetFromSlot(slot: AssetType): void {
  const selected = { ...state.selectedAssets }
  delete selected[slot]
  setState({ selectedAssets: selected })
}
