/**
 * 生成工作台参数偏好（Phase 0.27）：记住最近一次使用的尺寸/数量/Seed 模式。
 *
 * - 只持久化"参数"，不持久化 Prompt 内容（Prompt 属于作品，不应在刷新后残留）；
 * - 严格校验：字段非法/损坏 JSON 一律静默回退默认值，不影响页面；
 * - 与 Recipe / Workbench 快照 hydrate 无冲突：hydrate 显式带来的参数不会被写回偏好。
 */
export interface WorkbenchParams {
  width: number
  height: number
  count: number
  seedMode: 'random' | 'fixed'
  seed: number | null
}

export const WORKBENCH_PARAMS_KEY = 'generate.params.v1'

export const DEFAULT_WORKBENCH_PARAMS: WorkbenchParams = {
  width: 1024,
  height: 1024,
  count: 1,
  seedMode: 'random',
  seed: null,
}

const MIN_SIZE = 128
const MAX_SIZE = 4096
const MAX_COUNT = 64

function validSize(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) && value >= MIN_SIZE && value <= MAX_SIZE
    ? value
    : null
}

function validCount(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= MAX_COUNT
    ? value
    : null
}

function validSeed(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null
}

/** 读取参数偏好；任何异常/非法字段回退默认值。 */
export function loadWorkbenchParams(): WorkbenchParams {
  try {
    const raw = globalThis.localStorage?.getItem(WORKBENCH_PARAMS_KEY)
    if (!raw) return { ...DEFAULT_WORKBENCH_PARAMS }
    const parsed = JSON.parse(raw) as Record<string, unknown>
    if (!parsed || typeof parsed !== 'object') return { ...DEFAULT_WORKBENCH_PARAMS }
    const width = validSize(parsed.width)
    const height = validSize(parsed.height)
    const count = validCount(parsed.count)
    const seedMode = parsed.seedMode === 'fixed' ? 'fixed' : 'random'
    return {
      width: width ?? DEFAULT_WORKBENCH_PARAMS.width,
      height: height ?? DEFAULT_WORKBENCH_PARAMS.height,
      count: count ?? DEFAULT_WORKBENCH_PARAMS.count,
      seedMode,
      seed: seedMode === 'fixed' ? validSeed(parsed.seed) : null,
    }
  } catch {
    return { ...DEFAULT_WORKBENCH_PARAMS }
  }
}

/** 写入参数偏好；失败（隐私模式/配额满）静默忽略。 */
export function saveWorkbenchParams(params: WorkbenchParams): void {
  try {
    globalThis.localStorage?.setItem(WORKBENCH_PARAMS_KEY, JSON.stringify(params))
  } catch {
    // 记忆偏好失败不应影响生成主流程
  }
}
