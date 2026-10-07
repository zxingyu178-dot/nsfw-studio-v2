// 生成工作台导航注入契约（Prompt / Asset / Recipe → /generate 共用）
import type { WorkbenchSnapshot } from '../../types/workbench'

export interface WorkbenchNavigationState {
  /** Prompt / Asset / Recipe → 工作台 注入的统一快照（规范 §五十二） */
  workbench?: WorkbenchSnapshot
  sourceRecipeId?: string | null
  /** 注入前是否重置工作台（默认重置，保证 100% 恢复语义） */
  replace?: boolean
}
