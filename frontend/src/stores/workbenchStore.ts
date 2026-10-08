// 生成工作台统一状态（Phase 1 规范 §五十一、§五十二）。
// Prompt / Asset / Recipe（未来 Image / Agent）→ 生成工作台 都通过 WorkbenchSnapshot
// 注入本仓库，禁止把工作台状态散落在各组件。
import { useSyncExternalStore } from 'react'
import {
  emptyStructured,
  type AssetType,
  type InputImageRef,
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
   * Phase 5 增加 Reference 时只需在列表里多一个 Module（状态层不需要改）。
   * 普通新建：只携带 module_id；历史恢复（Task9）：携带完整执行身份。
   */
  workflowModules: WorkflowModuleRef[]
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

/** 保证模块列表始终包含基础生成，并按 Pipeline 固定顺序排列（基础生成 → 高清） */
function normalizeModules(modules: WorkflowModuleRef[], upscale: boolean): WorkflowModuleRef[] {
  const base = modules.filter((module) => module.module_id !== 'upscale')
  const withBase = base.length > 0 ? base : [{ module_id: 'basic_generate' } as WorkflowModuleRef]
  return upscale ? [...withBase, { module_id: 'upscale' }] : withBase
}

/** 当前状态 → 统一快照（保存 Prompt / 保存配方 / 提交 Job 时使用；模块身份原样保留，Task9） */
export function snapshotFromState(): WorkbenchSnapshot {
  return {
    prompt_mode: state.promptMode,
    structured_prompt: { ...state.structured },
    full_prompt: state.promptMode === 'full' ? state.fullPrompt : '',
    negative_prompt: state.negativePrompt,
    selected_assets: { ...state.selectedAssets },
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
    workflow_modules: state.workflowModules.map((module) => ({ ...module })),
    source_prompt_id: state.sourcePromptId,
    source_prompt_version_id: state.sourcePromptVersionId,
  }
}

/** 整体注入快照（Prompt / Recipe / Image / History → 工作台，100% 恢复，含模块身份 §十六/Task9） */
export function hydrateWorkbench(snapshot: WorkbenchSnapshot, sourceRecipeId: string | null = null): void {
  const modules = (snapshot.workflow_modules ?? []) as WorkflowModuleRef[]
  const inputImages = (snapshot.input_images ?? []).map((ref) => ({ ...ref }))
  setState({
    promptMode: snapshot.prompt_mode,
    structured: { ...emptyStructured(), ...snapshot.structured_prompt },
    fullPrompt: snapshot.full_prompt,
    negativePrompt: snapshot.negative_prompt,
    selectedAssets: { ...snapshot.selected_assets },
    // 带输入图恢复（配方 / 图库"用作输入图片"）→ 自动进入图片生成模式
    mode: inputImages.length > 0 ? 'image' : 'text',
    inputImages,
    width: snapshot.width,
    height: snapshot.height,
    count: snapshot.count,
    // Seed 默认 random；仅"使用此图 Seed"等显式固定时才恢复固定值（规范 §四十七）
    seedMode: typeof snapshot.seed === 'number' ? 'fixed' : 'random',
    seed: typeof snapshot.seed === 'number' ? snapshot.seed : null,
    workflowModules: normalizeModules(modules, hasUpscaleModule(modules)).map((module) => ({ ...module })),
    sourcePromptId: snapshot.source_prompt_id ?? null,
    sourcePromptVersionId: snapshot.source_prompt_version_id ?? null,
    sourceRecipeId,
  })
}

/** 清空工作台（新建） */
export function resetWorkbench(): void {
  state = initialState()
  listeners.forEach((listener) => listener())
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
  setState({ workflowModules: normalizeModules(state.workflowModules, enabled) })
}

/** 生成模式切换（§二十）：文生图 / 图片生成；切换保留输入图片（回到图片模式不丢选择） */
export function setWorkbenchMode(mode: WorkbenchMode): void {
  setState({ mode })
}

/** 设置输入图片（§七：max=1，选择新图即替换；来源必须是 Gallery image_id） */
export function setInputImage(imageId: string): void {
  setState({ inputImages: [{ role: 'source', image_id: imageId }], mode: 'image' })
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
