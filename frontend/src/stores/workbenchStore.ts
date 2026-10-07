// 生成工作台统一状态（Phase 1 规范 §五十一、§五十二）。
// Prompt / Asset / Recipe（未来 Image / Agent）→ 生成工作台 都通过 WorkbenchSnapshot
// 注入本仓库，禁止把工作台状态散落在各组件。
import { useSyncExternalStore } from 'react'
import {
  emptyStructured,
  type AssetType,
  type PromptMode,
  type SelectedAssetRef,
  type StructuredPrompt,
  type WorkbenchSnapshot,
} from '../types/workbench'

export interface WorkbenchState {
  promptMode: PromptMode
  structured: StructuredPrompt
  fullPrompt: string
  negativePrompt: string
  selectedAssets: Partial<Record<AssetType, SelectedAssetRef>>
  width: number
  height: number
  count: number
  seedMode: 'random'
  workflowModules: Record<string, unknown>[]
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
    width: 1024,
    height: 1024,
    count: 1,
    seedMode: 'random',
    workflowModules: [],
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

/** 当前状态 → 统一快照（保存 Prompt / 保存配方时使用） */
export function snapshotFromState(): WorkbenchSnapshot {
  return {
    prompt_mode: state.promptMode,
    structured_prompt: { ...state.structured },
    full_prompt: state.promptMode === 'full' ? state.fullPrompt : '',
    negative_prompt: state.negativePrompt,
    selected_assets: { ...state.selectedAssets },
    width: state.width,
    height: state.height,
    count: state.count,
    seed_mode: state.seedMode,
    workflow_modules: [...state.workflowModules],
    source_prompt_id: state.sourcePromptId,
    source_prompt_version_id: state.sourcePromptVersionId,
  }
}

/** 整体注入快照（Prompt / Recipe → 工作台，100% 恢复） */
export function hydrateWorkbench(snapshot: WorkbenchSnapshot, sourceRecipeId: string | null = null): void {
  setState({
    promptMode: snapshot.prompt_mode,
    structured: { ...emptyStructured(), ...snapshot.structured_prompt },
    fullPrompt: snapshot.full_prompt,
    negativePrompt: snapshot.negative_prompt,
    selectedAssets: { ...snapshot.selected_assets },
    width: snapshot.width,
    height: snapshot.height,
    count: snapshot.count,
    seedMode: 'random',
    workflowModules: [...(snapshot.workflow_modules ?? [])],
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
  setState({ count })
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
