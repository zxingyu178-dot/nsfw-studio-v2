import { STRUCTURED_FIELDS, type StructuredPrompt } from '../../../types/workbench'

/**
 * 解析 Prompt Console 的初始 active slot（v0.15.1 加固）。
 *
 * 优先级：localStorage 记忆（必须是合法 slot key）→ 第一个有内容的 slot → style。
 * 关键修复：旧版本/手工写入的记忆值（如 "foo"）不对应任何 slot，会导致 8 个 slot 全不 active；
 * 因此记忆值必须命中 STRUCTURED_FIELDS 的合法 key，否则视为无效并回退。
 */
export function resolveActiveSlot(structured: StructuredPrompt, stored: string | null): string {
  const validKeys: string[] = STRUCTURED_FIELDS.map((f) => f.key)
  if (stored !== null && validKeys.includes(stored)) {
    return stored
  }
  const firstFilled = STRUCTURED_FIELDS.find((f) => (structured[f.key] ?? '').trim().length > 0)
  return firstFilled?.key ?? 'style'
}
