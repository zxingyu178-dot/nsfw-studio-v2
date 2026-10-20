/**
 * Workbench 4.0 布局（v0.15 Task 1）：三栏宽度 + TaskDock 展开态 + Phase 0.17.1 左右栏收起。
 * 宽度/收起状态持久化到 localStorage；拖拽 ResizeHandle 时 clamp 到 min/max。
 * 断点（≥1200 可调 / 1024–1199 固定紧凑 / <1024 Workspace Tabs）主要由 CSS 决定。
 */
import { useSyncExternalStore } from 'react'

export const LEFT_DEFAULT = 320
export const RIGHT_DEFAULT = 300
export const LEFT_MIN = 280
export const LEFT_MAX = 420
export const RIGHT_MIN = 270
export const RIGHT_MAX = 380
export const LEFT_COMPACT = 280
export const RIGHT_COMPACT = 270
/** 收起态宽度（仅保留一条可点击展开的竖栏）。 */
export const COLLAPSED_WIDTH = 44

const LEFT_KEY = 'workbench.leftWidth'
const RIGHT_KEY = 'workbench.rightWidth'
const DOCK_KEY = 'workbench.taskDockOpen'
const LEFT_COLLAPSED_KEY = 'workbench.leftCollapsed'
const RIGHT_COLLAPSED_KEY = 'workbench.rightCollapsed'

export function clampWidth(width: number, min: number, max: number): number {
  if (!Number.isFinite(width)) return min
  return Math.min(max, Math.max(min, Math.round(width)))
}

export interface LayoutState {
  leftWidth: number
  rightWidth: number
  dockOpen: boolean
  leftCollapsed: boolean
  rightCollapsed: boolean
}

function readNumber(key: string, fallback: number): number {
  try {
    const raw = localStorage.getItem(key)
    if (raw === null) return fallback
    const n = Number(raw)
    return Number.isFinite(n) ? n : fallback
  } catch {
    return fallback
  }
}

function readBool(key: string, fallback: boolean): boolean {
  try {
    const raw = localStorage.getItem(key)
    return raw === null ? fallback : raw === '1'
  } catch {
    return fallback
  }
}

let state: LayoutState = {
  leftWidth: clampWidth(readNumber(LEFT_KEY, LEFT_DEFAULT), LEFT_MIN, LEFT_MAX),
  rightWidth: clampWidth(readNumber(RIGHT_KEY, RIGHT_DEFAULT), RIGHT_MIN, RIGHT_MAX),
  dockOpen: readBool(DOCK_KEY, false),
  leftCollapsed: readBool(LEFT_COLLAPSED_KEY, false),
  rightCollapsed: readBool(RIGHT_COLLAPSED_KEY, false),
}

const listeners = new Set<() => void>()

function setState(patch: Partial<LayoutState>): void {
  state = { ...state, ...patch }
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getLayoutState(): LayoutState {
  return state
}

export function useWorkbenchLayout(): LayoutState {
  return useSyncExternalStore(subscribe, getLayoutState)
}

function persist(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* 隐私模式等场景忽略持久化失败 */
  }
}

export function setLeftWidth(width: number): void {
  const next = clampWidth(width, LEFT_MIN, LEFT_MAX)
  if (next === state.leftWidth) return
  persist(LEFT_KEY, String(next))
  setState({ leftWidth: next })
}

export function setRightWidth(width: number): void {
  const next = clampWidth(width, RIGHT_MIN, RIGHT_MAX)
  if (next === state.rightWidth) return
  persist(RIGHT_KEY, String(next))
  setState({ rightWidth: next })
}

export function resetLeftWidth(): void {
  persist(LEFT_KEY, String(LEFT_DEFAULT))
  setState({ leftWidth: LEFT_DEFAULT })
}

export function resetRightWidth(): void {
  persist(RIGHT_KEY, String(RIGHT_DEFAULT))
  setState({ rightWidth: RIGHT_DEFAULT })
}

export function setDockOpen(open: boolean): void {
  if (open === state.dockOpen) return
  persist(DOCK_KEY, open ? '1' : '0')
  setState({ dockOpen: open })
}

export function toggleDock(): void {
  setDockOpen(!state.dockOpen)
}

/** Phase 0.17.1：左右栏收起/展开（收起后只保留 44px 竖栏，把空间让给 Canvas）。 */
export function setLeftCollapsed(collapsed: boolean): void {
  if (collapsed === state.leftCollapsed) return
  persist(LEFT_COLLAPSED_KEY, collapsed ? '1' : '0')
  setState({ leftCollapsed: collapsed })
}

export function setRightCollapsed(collapsed: boolean): void {
  if (collapsed === state.rightCollapsed) return
  persist(RIGHT_COLLAPSED_KEY, collapsed ? '1' : '0')
  setState({ rightCollapsed: collapsed })
}

export function toggleLeftCollapsed(): void {
  setLeftCollapsed(!state.leftCollapsed)
}

export function toggleRightCollapsed(): void {
  setRightCollapsed(!state.rightCollapsed)
}

/** 测试隔离：复位布局态。 */
export function __resetLayoutForTest(): void {
  try {
    localStorage.removeItem(LEFT_KEY)
    localStorage.removeItem(RIGHT_KEY)
    localStorage.removeItem(DOCK_KEY)
    localStorage.removeItem(LEFT_COLLAPSED_KEY)
    localStorage.removeItem(RIGHT_COLLAPSED_KEY)
  } catch {
    /* ignore */
  }
  state = {
    leftWidth: LEFT_DEFAULT,
    rightWidth: RIGHT_DEFAULT,
    dockOpen: false,
    leftCollapsed: false,
    rightCollapsed: false,
  }
  listeners.clear()
}
